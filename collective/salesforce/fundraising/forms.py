import copy
import datetime

from zope import schema
from zope.component import getMultiAdapter
from zope.interface import Interface
from zope.interface import invariant
from zope.interface import Invalid
from zope.component.hooks import getSite

from AccessControl.AuthEncoding import pw_encrypt
from AccessControl.SecurityManagement import newSecurityManager

from five import grok
from plone.directives import form
from zope.component import getUtility
from z3c.form import button, field
from z3c.form.browser import radio
from plone.directives import dexterity
from plone.dexterity.utils import createContentInContainer
from Products.statusmessages.interfaces import IStatusMessage
from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName

from dexterity.membrane.membrane_helpers import get_brains_for_email

from collective.simplesalesforce.utils import ISalesforceUtility

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign
from collective.salesforce.fundraising.personal_campaign_page import IPersonalCampaignPage
from collective.salesforce.fundraising.personal_campaign_page import IEditPersonalCampaignPage
from collective.salesforce.fundraising.person import IAddPerson
from collective.salesforce.fundraising.donor_quote import IDonorQuote
from collective.salesforce.fundraising.donation import IDonation
from collective.salesforce.fundraising.donation import ICreateOfflineDonation
from collective.salesforce.fundraising.donation import build_secret_key

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.utils import send_confirmation_email


class CreatePersonalCampaignPageForm(form.Form):
    grok.name('create-personal-campaign-page')
    grok.require('collective.salesforce.fundraising.AddPersonalCampaign')
    grok.context(IFundraisingCampaign)
    schema = IEditPersonalCampaignPage

    @property
    def fields(self):
        fields = field.Fields(IPersonalCampaignPage).select('title', 'description', 'image', 'goal', 'personal_appeal', 'thank_you_message')

        # Make the image field required
        image_field = copy.copy(fields['image'].field)
        image_field.required = True
        fields['image'].field = image_field

        # Set the default title.  Since the title field is defined in the model xml, it's easiest to do this here
        #mtool = getToolByName(self.context, 'portal_membership')
        #member = mtool.getAuthenticatedMember()
        #res = get_brains_for_email(self.context, member.getProperty('email'))
        #if not res:
        #    return None
        #person = res[0].getObject()
        #title_field = copy.copy(fields['title'].field)
        #title_field.default = u"%s %s's Fundraising Page" % (person.first_name, person.last_name)
        #fields['title'].field = title_field

        return fields

    ignoreContext = True

    label = _(u"Create My Fundraising Page")
    description = _(u"Set a goal and encourage your friends, family, and colleagues to donate towards your goal.")

    @button.buttonAndHandler(_(u'Create'))
    def handleOk(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        # Don't allow creation of a personal page if one already exists
        existing_personal_campaign = self.context.get_personal_fundraising_campaign_url()
        if existing_personal_campaign:
            messages = IStatusMessage(self.request)
            messages.add("You can't create more than one personal page per campaign.")
            self.request.response.redirect(self.context.absolute_url())
            return


        # Add a personal campaign within the current context,
        # using the data from the form.
        parent_campaign = self.context
        campaign = createContentInContainer(parent_campaign,
            'collective.salesforce.fundraising.personalcampaignpage',
            checkConstraints=False, **data)

        mtool = getToolByName(self.context, 'portal_membership')
        member = mtool.getAuthenticatedMember()
        person_res = get_brains_for_email(self.context, member.getProperty('email'))
        person = None
        contact_id = None
        if person_res:
            person = person_res[0].getObject()
            contact_id = person.sf_object_id
        
        settings = get_settings()

        # Add the campaign in Salesforce
        sfconn = getUtility(ISalesforceUtility).get_connection()
        data = {
            'Type': 'Personal Fundraising',
            'ParentId': parent_campaign.sf_object_id,
            'Name': data['title'],
            'Description': data['description'],
            'Public_Name__c': data['title'],
            'ExpectedRevenue': data['goal'],
            'Personal_Campaign_Contact__c': contact_id,
            'IsActive': True,
            'Status': 'In Progress',
            }
        if settings.sf_campaign_record_type_personal:
            data['RecordTypeID'] = settings.sf_campaign_record_type_personal

        res = sfconn.Campaign.create(data)
        if not res['success']:
            raise Exception(res['errors'][0])

        # Save the Id of the new campaign so it can be updated later.
        campaign.parent_sf_id = parent_campaign.sf_object_id
        campaign.sf_object_id = res['id']
        campaign.contact_sf_id = contact_id
        campaign.reindexObject()

        # Send email confirmation and links.
        campaign.send_email_personal_page_created()

        # Send the user to their new campaign.
        IStatusMessage(self.request).add(u'Welcome to your fundraising page!')
        self.request.response.redirect(campaign.absolute_url())

    @button.buttonAndHandler(_(u"Cancel"))
    def handleCancel(self, action):
        return

class EditPersonalCampaign(dexterity.EditForm):
    grok.name('edit-personal-campaign')
    grok.require('collective.salesforce.fundraising.EditPersonalCampaign')
    grok.context(IPersonalCampaignPage)

    label = _(u"Edit My Fundraising Page")
    description = _(u"Use the form below to edit your fundraising page to create the most effective appeal to your friends and family.")
    schema = IEditPersonalCampaignPage

class CreateDonorQuote(form.Form):
    grok.name('create-donor-quote')
    grok.require('collective.salesforce.fundraising.AddDonorQuote')
    grok.context(IFundraisingCampaign)

    @property
    def fields(self):
        return field.Fields(IDonorQuote).select('quote','name','image','contact_sf_id', 'donation_id', 'amount')

    ignoreContext = True

    label = _(u"Testimonial")
    description = _(u"Provide a quote to inspire others to give.")

    def updateWidgets(self):
        super(CreateDonorQuote, self).updateWidgets()
        self.widgets['contact_sf_id'].mode = 'hidden'
        self.widgets['donation_id'].mode = 'hidden'
        self.widgets['amount'].mode = 'hidden'

    @button.buttonAndHandler(_(u'Submit'))
    def handleOk(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return
        
        # Add a donor quote in the current context,
        # using the data from the form
        parent_campaign = self.context
        quote = createContentInContainer(parent_campaign,
            'collective.salesforce.fundraising.donorquote',
            checkConstraints=False, **data)
        
        mtool = getToolByName(self.context, 'portal_membership')
        contact_id = None
        if not mtool.isAnonymousUser():
            member = mtool.getAuthenticatedMember()
            contact_id = member.getProperty('sf_object_id')

        # Add the Constituent Quote to Salesforce
        sfconn = getUtility(ISalesforceUtility).get_connection()
        res = sfconn.Constituent_Quote__c.create({
            'Quote__c': data['quote'],
            'Name__c': data['name'],
            'Campaign__c': parent_campaign.sf_object_id,
            'Contact__c': data['contact_sf_id'],
            'Opportunity__c': data['donation_id'],
            'Amount__c': data['amount'],
        })

        if not res['success']:
            raise Exception(res['errors'][0])

        # Save the Id of the constituent quote so it can be updated
        quote.sf_object_id = res[0]['id']
        quote.parent_sf_id = parent_campaign.sf_object_id
        quote.reindexObject(idxs=['sf_object_id'])

        # Send the user back to the thank you page with a note about their quote
        # Hide the donor quote section of the thank you page
        IStatusMessage(self.request).add(u'Your story has been successfully submitted.')
        if data['donation_id'] and data['amount']:
            self.request.response.redirect(parent_campaign.absolute_url() + '/thank-you?hide=donorquote&donation_id=%s&amount=%s' % (data['donation_id'], data['amount']))
        else:
            self.request.response.redirect(parent_campaign.absolute_url() + '/thank-you?hide=donorquote')

class CreateDonationDonorQuote(form.Form):
    grok.name('create-donor-quote')
    grok.require('zope2.View')
    grok.context(IDonation)

    @property
    def action(self):
        """See interfaces.IInputForm"""
        return '%s/create-donor-quote' % self.context.absolute_url()

    @property
    def fields(self):
        return field.Fields(IDonorQuote).select('quote','name','image','key', 'amount')

    ignoreContext = True

    label = _(u"Testimonial")
    description = _(u"Provide a quote to inspire others to give.")

    def updateWidgets(self):
        super(CreateDonationDonorQuote, self).updateWidgets()
        self.widgets['key'].mode = 'hidden'
        self.widgets['amount'].mode = 'hidden'

    @button.buttonAndHandler(_(u'Submit'))
    def handleOk(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return
        donation = self.context

        if data['key'] != donation.secret_key:
            raise Unauthorized

        # Add a donor quote in the current context,
        # using the data from the form
        parent_campaign = donation.get_fundraising_campaign()
        quote = createContentInContainer(donation,
            'collective.salesforce.fundraising.donorquote',
            checkConstraints=False, **data)
        
        mtool = getToolByName(self.context, 'portal_membership')
        contact_id = None
        if not mtool.isAnonymousUser():
            member = mtool.getAuthenticatedMember()
            contact_id = member.getProperty('sf_object_id')

        quote.parent_sf_id = parent_campaign.sf_object_id

        # FIXME: This is not saving to Salesforce yet

        # Send the user back to the thank you page with a note about their quote
        # Hide the donor quote section of the thank you page
        IStatusMessage(self.request).add(u'Your story has been successfully submitted.')
        self.request.response.redirect('%s?hide=donorquote&key=%s' % (donation.absolute_url(), data['key']))


class ISetPassword(form.Schema):
    email = schema.TextLine(
        title=_(u"Email Address"),
        description=_(u""),
    )
    password = schema.Password(
        title=_(u"New Password"),
        description=_(u""),
    )
    password_confirm = schema.Password(
        title=_(u"Confirm New Password"),
        description=_(u""),
    )
    came_from = schema.TextLine(
        title=_(u"Redirect after login"),
        required=False,
    )

    form.mode(came_from='hidden')

    @invariant
    def passwordsInvariant(data):
        if data.password != data.password_confirm:
            raise Invalid(_(u"Your passwords do not match, please enter the same password in both fields"))

class SetPasswordForm(form.SchemaForm):
    grok.name('set-password-form')
    grok.context(ISiteRoot)

    schema = ISetPassword
    ignoreContext = True
    
    label = _(u"Set Your Password")
    description = _(u"Use the form below to set a password for your account which you can use in the future to log in.")

    def updateWidgets(self):
        super(SetPasswordForm, self).updateWidgets()
        self.widgets['email'].value = self.request.form.get('email', None)
        self.widgets['came_from'].value = self.request.form.get('came_from', None)

    @button.buttonAndHandler(_(u"Submit"))
    def handleOk(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        # NOTE: The validator on email should have already checked if the password can be set and auto logged the user in
        res = get_brains_for_email(self.context, data['email'], self.request)
        person = res[0].getObject()
        person.password = pw_encrypt(data['password'])
        person.registered = True

        # See if came_from was passed
        # fix odd bug where came_from is a list of two values
        came_from = data.get('came_from', None)
        if came_from and isinstance(came_from, (list, tuple)):
            came_from = came_from[0]

        self.request.form['came_from'] = came_from

        # merge in with standard plone login process.  
        login_next = self.context.restrictedTraverse('login_next')
        login_next()
            

@form.validator(field=ISetPassword['email'])
def validateEmail(value):
    site = getSite()

    res = get_brains_for_email(site, value)
    if not res:
        raise Invalid(_(u"No existing user account found to set password.  Please use the registration form to create an account."))

    # Auto log in the user
    # NOTE: This is to allow the current anon user access to the user profile.  If there is an error, you MUST log the user out before raising an exception
    mtool = getToolByName(site, 'portal_membership')
    acl = getToolByName(site, 'acl_users')
    newSecurityManager(None, acl.getUser(value))
    mtool.loginUser()

    person = res[0].getObject()

    if person.registered == True:
        mtool.logoutUser()
        raise Invalid(_(u"This account already has a password set.  If you have forgotten the password, please use the forgot password link to reset your password."))    

class AddPersonForm(form.SchemaForm):
    grok.name('create-user-account')
    grok.context(ISiteRoot)

    schema = IAddPerson
    ignoreContext = True

    label = _(u"Register a User Account")
    description = _(u"Use the form below to create your user account.")

    def updateWidgets(self):
        super(AddPersonForm, self).updateWidgets()
        self.widgets['email'].value = self.request.form.get('email', None)
        self.widgets['came_from'].value = self.request.form.get('came_from', None)

    @button.buttonAndHandler(_(u"Submit"))
    def handleOk(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        data = {
            'first_name': data['first_name'],
            'last_name': data['last_name'],
            'email': data['email'],
            'email_opt_in': data['email_opt_in'],
            'password': pw_encrypt(data['password']),
            'registered': True,
        }

        data_enc = {}
        for key, value in data.items():
            if key == 'email':
                data_enc[key] = value.encode('ascii')
                continue
            if isinstance(value, unicode):
                data_enc[key] = value.encode('utf8')
            else:
                data_enc[key] = value

   
        # Create the login user
        reg = getToolByName(self.context, 'portal_registration')
        props = {
            'fullname': '%s %s' % (data_enc['first_name'], data_enc['last_name']),
            'username': data_enc['email'],
            'email': data_enc['email'],
        }
        reg.addMember(data_enc['email'], data_enc['password'], properties=props) 

        # Create the user object
        people_container = getattr(getSite(), 'people')
        person = createContentInContainer(
            people_container,
            'collective.salesforce.fundraising.person',
            checkConstraints=False,
            **data
        )

        # Authenticate the user
        mtool = getToolByName(self.context, 'portal_membership')
        acl = getToolByName(self.context, 'acl_users')
        newSecurityManager(None, acl.getUser(data_enc['email']))
        mtool.loginUser()

        # See if came_from was passed
        # fix odd bug where came_from is a list of two values
        came_from = self.request.form.get('form.widgets.came_from', None)
        if came_from and isinstance(came_from, (list, tuple)):
            came_from = came_from[0]

        if came_from:
            self.request.form['came_from'] = came_from

        # merge in with standard plone login process.  
        login_next = self.context.restrictedTraverse('login_next')
        login_next()


class CreateOfflineDonation(form.Form):
    grok.name('create-offline-donation')
    grok.require('collective.salesforce.fundraising.EditPersonalCampaign')
    grok.context(IPersonalCampaignPage)
    schema = ICreateOfflineDonation

    fields = field.Fields(ICreateOfflineDonation)
    fields['payment_method'].widgetFactory = radio.RadioFieldWidget

    ignoreContext = True

    label = _(u"Add Offline Donation")
    description = _(u"If you have raised money offline via cash or check, enter them here so you get credit towards your goal")

    @button.buttonAndHandler(_(u'Submit'))
    def handleOk(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        data['title'] = '%s %s - One-time Offline Donation' % (data['first_name'], data['last_name'])
        data['secret_key'] = build_secret_key()
        data['stage'] = 'Pledged'
        data['products'] = []
        data['campaign_sf_id'] = self.context.sf_object_id
        data['payment_date'] = datetime.date.today()
        data['transaction_id'] = 'offline:' + data['secret_key']
        data['offline'] = True
 
        # Add a donation in the current context,
        # using the data from the form
        parent_campaign = self.context
        donation = createContentInContainer(parent_campaign,
            'collective.salesforce.fundraising.donation',
            checkConstraints=False, **data)

        # Add the donation to the campaign totals
        #self.context.add_donation(data['amount'])
        
        IStatusMessage(self.request).add(u'Your offline gift was entered and will be counted in your total raised. The gift and donor contact information will appear in "My Donors" shortly.')
        self.request.response.redirect(parent_campaign.absolute_url())


import copy

from zope import schema
from zope.component import getMultiAdapter
from zope.interface import Interface
from zope.interface import invariant
from zope.interface import Invalid
from zope.site.hooks import getSite

from AccessControl.AuthEncoding import pw_encrypt
from AccessControl.SecurityManagement import newSecurityManager

from five import grok
from plone.directives import form
from z3c.form import button, field
from plone.directives import dexterity
from plone.dexterity.utils import createContentInContainer
from Products.statusmessages.interfaces import IStatusMessage
from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName

from dexterity.membrane.membrane_helpers import get_brains_for_email

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign
from collective.salesforce.fundraising.personal_campaign_page import IPersonalCampaignPage
from collective.salesforce.fundraising.personal_campaign_page import IEditPersonalCampaignPage
from collective.salesforce.fundraising.person import IAddPerson
from collective.salesforce.fundraising.donor_quote import IDonorQuote

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
        if not person_res:
            contact_id = None
        else: 
            contact_id = person_res[0].getObject().sf_object_id

        settings = get_settings()

        # Add the campaign in Salesforce
        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
        data = {
            'type': 'Campaign',
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

        res = sfbc.create(data)
        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        # Save the Id of the new campaign so it can be updated later.
        campaign.parent_sf_id = parent_campaign.sf_object_id
        campaign.sf_object_id = res[0]['id']
        campaign.reindexObject(idxs=['sf_object_id'])

        # Send email confirmation and links.
        data['parent'] = parent_campaign
        data['campaign'] = campaign
        data['FirstName'] = member.getProperty('fullname', 'friend')
        email_view = getMultiAdapter((campaign, self.request), name='page-confirmation-email')
        email_view.set_page_values(data)
        email_body = email_view()
        email_to = member.getProperty('email')
        subject = 'New Personal Campaign Page Created'
        send_confirmation_email(campaign, subject, email_to, email_body)

        # Send the user to their new campaign.
        IStatusMessage(self.request).add(u'Welcome to your personal campaign page!')
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

#    @button.buttonAndHandler(_(u"Save Changes"))
#    def handleSaveChanges(self, action):
#        data, errors = self.extractData()
#        if errors:
#            self.status = self.formErrorsMessage
#            return
#
#
#        settings = get_settings()
#
#        changed = False
#        if data['title'] != self.context.Title():
#            changed = True
#        if data['description'] != self.context.Description():
#            changed = True
#        if data['goal'] != self.context.goal:
#            changed = True
#
#        if changed:
#            # Update the campaign in Salesforce
#            sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
#            data = {
#                'type': 'Campaign',
#                'id': self.context.sf_object_id,
#                'Name': data['title'],
#                'Description': data['description'],
#                'Public_Name__c': data['title'],
#                'ExpectedRevenue': data['goal'],
#                }
#
#            res = sfbc.update(data)
#            if not res[0]['success']:
#                raise Exception(res[0]['errors'][0]['message'])
#
#        campaign.reindexObject()
#
#        # Send the user to their new campaign.
#        IStatusMessage(self.request).add(u'Your changes have been saved.  You can see your changes below.!')
#        self.request.response.redirect(self.context.absolute_url())
#        return
#
#    @button.buttonAndHandler(_(u"Cancel"))
#    def handleCancel(self, action):
#        return


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
        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
        res = sfbc.create({
            'type': 'Constituent_Quote__c',
            'Quote__c': data['quote'],
            'Name__c': data['name'],
            'Campaign__c': parent_campaign.sf_object_id,
            'Contact__c': data['contact_sf_id'],
            'Opportunity__c': data['donation_id'],
            'Amount__c': data['amount'],
        })

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

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
   
        # Create the login user
        reg = getToolByName(self.context, 'portal_registration')
        props = {
            'fullname': u'%s %s' % (data['first_name'], data['last_name']),
            'username': data['email'],
            'email': data['email'],
        }
        reg.addMember(data['email'], data['password'], properties=props) 

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
        newSecurityManager(None, acl.getUser(data['email']))
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

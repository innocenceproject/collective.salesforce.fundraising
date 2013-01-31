import random
import string
from five import grok
from zope import schema
from AccessControl import Unauthorized
from zope.interface import alsoProvides
from zope.component import getUtility
from zope.component import getMultiAdapter
from zope.site.hooks import getSite
from zope.app.content.interfaces import IContentType
from plone.uuid.interfaces import IUUID
from plone.app.uuid.utils import uuidToObject
from plone.namedfile.field import NamedImage
from Products.CMFCore.utils import getToolByName
from plone.i18n.locales.countries import CountryAvailability
from plone.directives import dexterity, form
from plone.formwidget.contenttree.source import ObjPathSourceBinder
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.z3cform.interfaces import IWrappedForm
from z3c.relationfield import RelationList
from z3c.relationfield import RelationValue
from z3c.relationfield.schema import RelationChoice
from plone.namedfile.interfaces import IImageScaleTraversable
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.us_states import states_list
from collective.salesforce.fundraising.janrain.rpx import SHARE_JS_TEMPLATE

def build_secret_key():
    return ''.join(random.choice(string.ascii_letters + string.digits) for x in range(32))

@grok.provider(schema.interfaces.IContextSourceBinder)
def availablePeople(context):
    query = {
        "portal_type": "collective.salesforce.fundraising.person",
    }
    return ObjPathSourceBinder(**query).__call__(context)

@grok.provider(schema.interfaces.IContextSourceBinder)
def availableCampaigns(context):
    #campaign = context.get_fundraising_campaign()
    query = {
        "portal_type": [
            "collective.salesforce.fundraising.fundraising_campaign",
            "collective.salesforce.fundraising.personal_campaign_page",
        ],
        #"UUID": IUUID(campaign),
    }
    return ObjPathSourceBinder(**query).__call__(context)

class IDonation(form.Schema, IImageScaleTraversable):
    """
    A donation linked to its originating campaign and user
    """
    person = RelationChoice(
        title=u"Donor",
        description=u"The user account of the donor",
        required=False,
        source=availablePeople,
    )

    campaign = RelationChoice(
        title=u"Campaign",
        description=u"The campaign this is related to",
        required=False,
        source=availableCampaigns,
    )

    products = schema.List(
        title=u"Products",
        description=u"Format: ProductUID|Price|Quantity",
        required=False,
        value_type=schema.TextLine(),
    )

    is_recurring = schema.Bool(
        title=u"Is Recurring?",
        description=u"Is this a recurring donation?",
        required=False,
        default=False,
    )

    recurring_plan_id = schema.TextLine(
        title=u"Recurring Plan ID",
        description=u"If this is a recurring donation, this is set to the ID of the plan",
    )

    form.model("models/donation.xml")
alsoProvides(IDonation, IContentType)


class Donation(dexterity.Container):
    grok.implements(IDonation)

    def get_container(self):
        if not self.campaign_sf_id:
            return None
        site = getSite()
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(
            sf_object_id=self.campaign_sf_id, 
            portal_type = ['collective.salesforce.fundraising.fundraisingcampaign','collective.salesforce.fundraising.personalcampaignpage'],
        )
        if not res:
            return None
        return res[0].getObject()


    def send_donation_receipt(self, key):
        settings = get_settings()
        
        # Construct the email bodies
        pt = getToolByName(self, 'portal_transforms')
        email_view = getMultiAdapter((self, request), name='thank-you-email')
        email_view.set_donation_key(key)
        email_body = email_view()
        txt_body = pt.convertTo('text/-x-web-intelligent', email_body, mimetype='text/html')

        # Determine to and from addresses
        portal_url = getToolByName(self, 'portal_url')
        portal = portal_url.getPortalObject()
        mail_from = '"%s" <%s>' % (portal.getProperty('email_from_name'), portal.getProperty('email_from_address'))
        if not self.context.person or not self.context.person.to_object:
            # Skip if we have no email to send to
            return
        mail_to = self.context.person.to_object.email

        # Construct the email message                
        msg = MIMEMultipart('alternative')
        msg['Subject'] = settings.thank_you_email_subject
        msg['From'] = mail_from
        msg['To'] = mail_to
        part1 = MIMEText(txt_body, 'plain')
        part2 = MIMEText(email_body, 'html')

        msg.attach(part1)
        msg.attach(part2)

        # Attempt to send it
        try:
            host = getToolByName(self, 'MailHost')
            # The `immediate` parameter causes an email to be sent immediately
            # (if any error is raised) rather than sent at the transaction
            # boundary or queued for later delivery.
            host.send(msg, immediate=True)

        except smtplib.SMTPRecipientsRefused:
            # fail silently so errors here don't freak out the donor about their transaction which was successful by this point
            pass

    def get_fundraising_campaign(self):
        if self.campaign and self.campaign.to_object:
            return self.campaign.to_object


class ThankYouView(grok.View):
    grok.context(IDonation)
    grok.require('zope2.View')

    grok.name('view')
    grok.template('thank-you')

    def update(self):
        # Fetch some values that should have been passed from the redirector
        key = self.request.form.get('key', None)

        if not key or key != self.context.secret_key:
            raise Unauthorized

        self.receipt_view = None
        self.receipt = None
        self.receipt_view = getMultiAdapter((self.context, self.request), name='receipt')
        self.receipt_view.set_donation_key(key)
        self.receipt = self.receipt_view()

        # Create a wrapped form for inline rendering
        from collective.salesforce.fundraising.forms import CreateDonationDonorQuote
        # Only show the form if a donor quote can be created
        if self.context.can_create_donor_quote():
            self.donor_quote_form = CreateDonationDonorQuote(self.context, self.request)
            alsoProvides(self.donor_quote_form, IWrappedForm)
            self.donor_quote_form.update()
            self.donor_quote_form.widgets.get('name').value = u'%s %s' % (self.receipt_view.person.first_name, self.receipt_view.person.last_name)
            self.donor_quote_form.widgets.get('contact_sf_id').value = unicode(self.receipt_view.person.sf_object_id)
            self.donor_quote_form.widgets.get('key').value = unicode(self.context.secret_key)
            self.donor_quote_form.widgets.get('amount').value = int(self.context.amount)
            self.donor_quote_form_html = self.donor_quote_form.render()

        # Determine any sections that should be collapsed
        self.hide = self.request.form.get('hide', [])
        if self.hide:
            self.hide = self.hide.split(',')

    def render_janrain_share(self):
        settings = get_settings()
        comment = settings.thank_you_share_message
        if not comment:
            comment = ''

        amount_str = ''
        amount_str = u' $%s' % self.context.amount
        comment = comment.replace('{{ amount }}', str(self.context.amount))

        campaign = self.context.get_fundraising_campaign()
        if not campaign:
            return ''
        
        return SHARE_JS_TEMPLATE % {
            'link_id': 'share-message-thank-you',
            'url': campaign.absolute_url() + '?SOURCE_CODE=thank_you_share',
            'title': campaign.title.replace("'","\\'"),
            'description': campaign.description.replace("'","\\'"),
            'image': campaign.absolute_url() + '/@@images/image',
            'message': comment,
        }

class HonoraryMemorialView(grok.View):
    grok.context(IDonation)
    grok.require('zope2.View')

    grok.name('honorary-memorial-donation')

    form_template = ViewPageTemplateFile('donation_templates/honorary-memorial-donation.pt')

    def render(self):
        key = self.request.form.get('key', None)

        if not key or key != self.context.secret_key:
            raise Unauthorized

        self.receipt_view = getMultiAdapter((self.context, self.request), name='receipt')
        self.receipt_view.set_donation_key(key)
        self.receipt = self.receipt_view()

        # Handle POST
        if self.request['REQUEST_METHOD'] == 'POST':
            # Fetch values from the request
            self.context.honorary_type = self.request.form.get('honorary_type', None)
            self.context.honorary_notification_type = self.request.form.get('honorary_notification_type', None)
            self.context.honorary_first_name = self.request.form.get('honorary_first_name', None)
            self.context.honorary_last_name = self.request.form.get('honorary_last_name', None)
            self.context.honorary_recipient_first_name = self.request.form.get('honorary_recipient_first_name', None)
            self.context.honorary_recipient_last_name = self.request.form.get('honorary_recipient_last_name', None)
            self.context.honorary_email = self.request.form.get('honorary_email', None)
            self.context.honorary_address = self.request.form.get('honorary_address', None)
            self.context.honorary_city = self.request.form.get('honorary_city', None)
            self.context.honorary_state = self.request.form.get('honorary_state', None)
            self.context.honorary_zip = self.request.form.get('honorary_zip', None)
            self.context.honorary_country = self.request.form.get('honorary_country', None)
            self.context.honorary_message = self.request.form.get('honorary_message', None)

            # If there was an email passed and we're supposed to send an email, send the email
            if self.context.honorary_notification_type == 'Email' and self.context.honorary_email:

                settings = get_settings() 

                # Construct the email bodies
                pt = getToolByName(self.context, 'portal_transforms')
                if self.context.honorary_type == u'Honorary':
                    email_view = getMultiAdapter((self.context, self.request), name='honorary-email')
                else:
                    email_view = getMultiAdapter((self.context, self.request), name='memorial-email')

                person = self.context.person
                if person:
                    person = person.to_object

                email_body = email_view()
        
                txt_body = pt.convertTo('text/-x-web-intelligent', email_body, mimetype='text/html')

                # Construct the email message                
                portal_url = getToolByName(self.context, 'portal_url')
                portal = portal_url.getPortalObject()

                mail_from = '"%s" <%s>' % (portal.getProperty('email_from_name'), portal.getProperty('email_from_address'))
                mail_cc = None
                if self.context.person and self.context.person.to_object:
                    mail_cc = self.context.person.to_object.email

                msg = MIMEMultipart('alternative')
                subject_vars = {'first_name': self.context.honorary_first_name, 'last_name': self.context.honorary_last_name}
                if self.context.honorary_type == 'Memorial': 
                        msg['Subject'] = 'Gift received in memory of %(first_name)s %(last_name)s' % subject_vars
                else:
                    msg['Subject'] = 'Gift received in honor of %(first_name)s %(last_name)s' % subject_vars
                msg['From'] = mail_from
                msg['To'] = self.context.honorary_email
                if mail_cc:
                    msg['Cc'] = mail_cc
    
                part1 = MIMEText(txt_body, 'plain')
                part2 = MIMEText(email_body, 'html')

                msg.attach(part1)
                msg.attach(part2)

                # Attempt to send it
                try:

                    # Send the notification email
                    host = getToolByName(self, 'MailHost')
                    host.send(msg, immediate=True)

                except smtplib.SMTPRecipientsRefused:
                    # fail silently so errors here don't freak out the donor about their transaction which was successful by this point
                    pass

            # Redirect on to the thank you page
            self.request.response.redirect('%s?key=%s' % (self.context.absolute_url(), self.context.secret_key))

        self.countries = CountryAvailability().getCountryListing()
        self.countries.sort()

        self.states = states_list

        return self.form_template()

class DonationReceipt(grok.View):
    """ Renders an html receipt for a donation.  This is intended to be embedded in another view

    Uses a random key in url to authenticate access
    """
    grok.context(IDonation)
    grok.require('zope2.View')

    grok.name('receipt')
    grok.template('receipt')

    def update(self):
        key = getattr(self, 'key', None)
        if not key:
            self.set_donation_key()
            key = getattr(self, 'key', None)

        if not key or key != self.context.secret_key:
            raise Unauthorized

        settings = get_settings()
        self.organization_name = settings.organization_name
        self.donation_receipt_legal = settings.donation_receipt_legal
        if getattr(self.context, 'donation_receipt_legal', None):
            self.donation_receipt_legal = self.context.donation_receipt_legal

        self.person = self.context.person
        if self.person:
            self.person = self.context.person.to_object

        self.products = []
        if self.context.products:
            for product in self.context.products:
                price, quantity, product_uuid = product.split('|', 2)
                total = int(price) * int(quantity)
                product = uuidToObject(product_uuid)
                if product.donation_only:
                    price = total
                    quantity = '-'
                self.products.append({
                    'price': price,
                    'quantity': quantity,
                    'product': product,
                    'total': total,
                })

    def set_donation_key(self, key=None):
        self.key = self.request.form.get('key', key)


class ThankYouEmail(grok.View):
    grok.context(IDonation)
    grok.require('zope2.View')
    
    grok.name('thank-you-email')
    grok.template('thank-you-email')
    
    def update(self):
        
        key = getattr(self, 'key', None)
        if not key:
            self.set_donation_key()
            key = getattr(self, 'key', None)

        if not key or key != self.context.secret_key:
            raise Unauthorized

        self.receipt_view = getMultiAdapter((self.context, self.request), name='receipt')
        self.receipt_view.set_donation_key(key)
        self.receipt = self.receipt_view()

        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer

    def set_donation_key(self, key=None):
        # Do nothing if already set
        if getattr(self, 'key', None):
            return

        self.key = self.request.form.get('key', key)


class HonoraryEmail(grok.View):
    grok.context(IDonation)
    grok.require('zope2.View')
    
    grok.name('honorary-email')
    grok.template('honorary-email')
    
    def update(self):
        key = getattr(self, 'key', None)
        if not key:
            self.set_donation_key()
            key = getattr(self, 'key', None)

        if not key or key != self.context.secret_key:
            raise Unauthorized

        self.set_honorary_info()
            
        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer
        self.organization_name = settings.organization_name
        self.amount = None
        if self.request.form.get('show_amount', None) == 'Yes':
            self.amount = self.context.amount
        
    def set_honorary_info(self):
        self.donor = self.context.person.to_object

        if self.request.get('show_template', None) == 'true':
            self.honorary = {
                'first_name': '[Memory Name]',
                'last_name': '[Memory Name]',
                'recipient_first_name': '[Recipient First Name]',
                'recipient_last_name': '[Recipient Last Name]',
                'message': '[Message]',
            }
        else:
            self.honorary = {
                'first_name': self.context.honorary_first_name,
                'last_name': self.context.honorary_last_name,
                'recipient_first_name': self.context.honorary_recipient_first_name,
                'recipient_last_name': self.context.honorary_recipient_last_name,
                'message': self.context.honorary_message,
            }

        # Attempt to perform a basic text to html conversion on the message text provided
        pt = getToolByName(self.context, 'portal_transforms')
        if self.honorary.get('message'):
            try:
                self.honorary['message'] = pt.convertTo('text/html', self.honorary['message'], mimetype='text/-x-web-intelligent')
            except:
                self.honorary['message'] = honorary['message']

    def set_donation_key(self, key=None):
        # Do nothing if already set
        if getattr(self, 'key', None):
            return

        self.key = self.request.form.get('key', key)


#FIXME: I tried to use subclasses to build these 2 views but grok seemed to be getting in the way.
# I tried making a base mixin class then 2 different views base of it and grok.View as well as 
# making MemorialEmail subclass Honorary with a new name and template.  Neither worked so I'm 
# left duplicating logic for now.
class MemorialEmail(grok.View):
    grok.context(IDonation)
    grok.require('zope2.View')
    
    grok.name('memorial-email')
    grok.template('memorial-email')

    def update(self):
        key = getattr(self, 'key', None)
        if not key:
            self.set_donation_key()
            key = getattr(self, 'key', None)

        if not key or key != self.context.secret_key:
            raise Unauthorized

        self.set_honorary_info()
            
        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer
        self.organization_name = settings.organization_name
        self.amount = None
        if self.request.form.get('show_amount', None) == 'Yes':
            self.amount = self.context.amount
        
    def set_honorary_info(self):
        self.donor = self.context.person.to_object

        if self.request.get('show_template', None) == 'true':
            self.honorary = {
                'first_name': '[Memory Name]',
                'last_name': '[Memory Name]',
                'recipient_first_name': '[Recipient First Name]',
                'recipient_last_name': '[Recipient Last Name]',
                'message': '[Message]',
            }
        else:
            self.honorary = {
                'first_name': self.context.honorary_first_name,
                'last_name': self.context.honorary_last_name,
                'recipient_first_name': self.context.honorary_recipient_first_name,
                'recipient_last_name': self.context.honorary_recipient_last_name,
                'message': self.context.honorary_message,
            }

        # Attempt to perform a basic text to html conversion on the message text provided
        pt = getToolByName(self.context, 'portal_transforms')
        if self.honorary.get('message'):
            try:
                self.honorary['message'] = pt.convertTo('text/html', self.honorary['message'], mimetype='text/-x-web-intelligent')
            except:
                self.honorary['message'] = honorary['message']

    def set_donation_key(self, key=None):
        # Do nothing if already set
        if getattr(self, 'key', None):
            return

        self.key = self.request.form.get('key', key)


def post_process_donation(donation):

    # Lookup the Campaign
    pc = getToolByName(donation.context, 'portal_catalog')
    res = pc.searchResults(
        sf_object_id = donation.campaign_sf_id,
        portal_type = ['collective.salesforce.fundraising.fundraisingcampaign','collective.salesforce.fundraising.personalcampaignpage'],
    )

    campaign = res[0].getObject()
    # FIXME: What happens if lookup fails?

    sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')

    # Handle Donation Product forms
    product = None
    product_id = self.request.form.get('c_product_id', None)
    c_products = self.request.form.get('c_products', None)
    quantity = self.request.form.get('c_quantity', None)
    pricebook_id = None
    if product_id:
        res = pc.searchResults(sf_object_id=product_id, portal_type='collective.salesforce.fundraising.donationproduct')
        if not res:
            return 'ERROR: Product with ID %s not found' % product_id
        product = res[0].getObject()

        if product_id or c_products:
            pricebook_id = get_standard_pricebook_id(sfbc)

        # Handle Product Forms with multiple products, each with their own quantity
        products = []
        if c_products:
            for item in c_products.split(','):
                item_id, item_quantity = item.split(':')
                product_res = pc.searchResults(sf_object_id = item_id, portal_type='collective.salesforce.fundraising.donationproduct')
                if not product_res:
                    return 'ERROR: Product with ID %s not found' % product_id
                products.append({'id': item_id, 'quantity': item_quantity, 'product': product_res[0].getObject()})

        settings = get_settings()

        # Look for an existing Plone user
        mt = getToolByName(self.context, 'portal_membership')
        first_name = self.request.form.get('first_name', None)
        last_name = self.request.form.get('last_name', None)

        # lowercase all email addresses to avoid lookup errors if typed with different caps
        email = self.request.form.get('email', None)
        if email:
            email = email.lower()

        email_opt_in = self.request.form.get('email_signup', None) == 'YES'
        phone = self.request.form.get('phone', None)
        address = self.request.form.get('address', None)
        city = self.request.form.get('city', None)
        state = self.request.form.get('state', None)
        zipcode = self.request.form.get('zip', None)
        country = self.request.form.get('country', None)
        amount = int(float(self.request.form.get('x_amount', None)))

        res = get_brains_for_email(self.context, email, self.request)
        # If no existing user, create one which creates the contact in SF (1 API call)
        if not res:
            data = {
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'address': address,
                'city': city,
                'state': state,
                'zip': zipcode,
                'country': country,
                'phone': phone,
            }

            # Treat the email_opt_in field as a ratchet.  Once toggled on, it stays on even if unchecked
            # on a subsequent donation.  Unsubscribing is the way to prevent emails.
            if email_opt_in:
                data['email_opt_in'] = email_opt_in

            # Create the user
            people_container = getattr(getSite(), 'people')
            person = createContentInContainer(
                people_container,
                'collective.salesforce.fundraising.person',
                checkConstraints=False,
                **data
            )

        # If existing user, fill with updated data from subscription profile (1 API call, Person update handler)
        else:
            # Authenticate the user temporarily to fetch their person object with some level of permissions applied
            mtool = getToolByName(self.context, 'portal_membership')
            acl = getToolByName(self.context, 'acl_users')
            newSecurityManager(None, acl.getUser(email))
            mtool.loginUser()

            # See if any values are modified and if so, update the Person and upsert the changes to SF
            person = res[0].getObject()
            old_data = [person.address, person.city, person.state, person.zip, person.country, person.phone]
            new_data = [address, city, state, zipcode, country, phone]

            if new_data != old_data:
                person.address = address
                person.city = city
                person.state = state
                person.zip = zipcode
                person.country = country
                person.phone = phone
                person.reindexObject()

                person.upsertToSalesforce()

            mtool.logoutUser()

        

        # Create the Opportunity object and Opportunity Contact Role (2 API calls)

        transaction_id = None
        data = {
            'type': 'Opportunity',
            'AccountId': settings.sf_individual_account_id,
            'Success_Transaction_Id__c': self.stripe_result['id'],
            'Amount': amount,
            'Name': '%s %s - $%i One Time Donation' % (first_name, last_name, amount),
            'StageName': 'Posted',
            'CloseDate': datetime.now(),
            'CampaignId': campaign.sf_object_id,
            'Source_Campaign__c': campaign.get_source_campaign(),
            'Source_Url__c': campaign.get_source_url(),
        }

        if product_id and product is not None:
            # FIXME: Add custom record type for Stripe Donations
            # record product donations as a particular type, if possible
            if settings.sf_opportunity_record_type_product:
                data['RecordTypeID'] = settings.sf_opportunity_record_type_product
            # Set the pricebook on the Opportunity to the standard pricebook
            data['Pricebook2Id'] = pricebook_id

            # Set amount to 0 since the amount is incremented automatically by Salesforce
            # when an OpportunityLineItem is created against the Opportunity
            data['Amount'] = 0

            # Set a custom name with the product info and quantity
            data['Name'] = '%s %s - %s (Qty %s)' % (first_name, last_name, product.title, quantity)

        elif products:
            # record product donations as a particular type, if possible
            if settings.sf_opportunity_record_type_product:
                data['RecordTypeID'] = settings.sf_opportunity_record_type_product
            # Set the pricebook on the Opportunity to the standard pricebook
            data['Pricebook2Id'] = pricebook_id

            # Set amount to 0 since the amount is incremented automatically by Salesforce
            # when an OpportunityLineItem is created against the Opportunity
            data['Amount'] = 0

            # Set a custom name with the product info and quantity
            parent_form = products[0]['product'].get_parent_product_form()
            title = 'Donation'
            if parent_form:
                title = parent_form.title
            data['Name'] = '%s %s - %s' % (first_name, last_name, title)
            
        else:
            # this is a one-time donation, record it as such if possible
            if settings.sf_opportunity_record_type_one_time:
                data['RecordTypeID'] = settings.sf_opportunity_record_type_one_time


        res = sfbc.create(data)

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        opportunity = res[0]

        role_res = sfbc.create({
        'type': 'OpportunityContactRole',
            'OpportunityId': opportunity['id'],
            'ContactId': person.sf_object_id,
            'IsPrimary': True,
            'Role': 'Decision Maker',
        })

        if not role_res[0]['success']:
            raise Exception(role_res[0]['errors'][0]['message'])

        # If there is a product, add the OpportunityLineItem (1 API Call)
        if product_id and product is not None:
            line_item_res = sfbc.create({
                'type': 'OpportunityLineItem',
                'OpportunityId': opportunity['id'],
                'PricebookEntryId': product.pricebook_entry_sf_id,
                'UnitPrice': product.price,
                'Quantity': quantity,
            })
            
            if not line_item_res[0]['success']:
                raise Exception(line_item_res[0]['errors'][0]['message'])

        # If there are Products from a Product Form, create the OpportunityLineItems (1 API Call)
        if products:
            line_items = []
            for item in products:
                line_item = {
                    'type': 'OpportunityLineItem',
                    'OpportunityId': opportunity['id'],
                    'PricebookEntryId': item['product'].pricebook_entry_sf_id,
                    'UnitPrice': item['product'].price,
                    'Quantity': item['quantity'],
                }
                line_items.append(line_item)
            
            line_item_res = sfbc.create(line_items)
            
            if not line_item_res[0]['success']:
                raise Exception(line_item_res[0]['errors'][0]['message'])

        # Create the Campaign Member (1 API Call).  Note, we ignore errors on this step since
        # trying to add someone to a campaign that they're already a member of throws
        # an error.  We want to let people donate more than once.
        # Ignoring the error saves an API call to first check if the member exists
        if settings.sf_create_campaign_member:
            role_res = sfbc.create({
                'type': 'CampaignMember',
                'CampaignId': campaign.sf_object_id,
                'ContactId': person.sf_object_id,
                'Status': 'Responded',
            })

        # Record the transaction and its amount in the campaign
        campaign.add_donation(amount)

        # Send the email receipt
        # FIXME: Disabled for testing
        #campaign.send_donation_receipt(self.request, opportunity['id'], amount)

        # If this is an honorary or memorial donation, redirect to the form to provide details
        is_honorary = self.request.form.get('is_honorary', None)
        if is_honorary == 'true':
            redirect_url = '%s/honorary-memorial-donation?donation_id=%s&amount=%s' % (campaign.absolute_url(), opportunity['id'], amount)
        else:
            redirect_url = '%s?donation_id=%s&amount=%s' % (campaign.absolute_url(), opportunity['id'], amount)

        return redirect_url




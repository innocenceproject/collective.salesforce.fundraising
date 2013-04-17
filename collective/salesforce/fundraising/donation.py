import random
import string
from datetime import datetime
from five import grok
from zope import schema
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from AccessControl import Unauthorized
from Acquisition import aq_base
from zope.interface import alsoProvides
from zope.interface import Interface
from zope.component import getUtility
from zope.component import getMultiAdapter
from zope.site.hooks import getSite
from zope.app.intid.interfaces import IIntIds
from zope.app.content.interfaces import IContentType
from zope.app.container.interfaces import IObjectAddedEvent
from zope.event import notify
from zope.lifecycleevent.interfaces import IObjectModifiedEvent
from zope.lifecycleevent import ObjectModifiedEvent
from AccessControl.SecurityManagement import newSecurityManager
from plone.uuid.interfaces import IUUID
from plone.app.uuid.utils import uuidToObject
from plone.app.async.interfaces import IAsyncService
from plone.namedfile.field import NamedImage
from Products.CMFCore.utils import getToolByName
from plone.i18n.locales.countries import CountryAvailability
from plone.directives import dexterity, form
from plone.dexterity.utils import createContentInContainer
from plone.formwidget.contenttree.source import ObjPathSourceBinder
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.z3cform.interfaces import IWrappedForm
from z3c.relationfield import RelationList
from z3c.relationfield import RelationValue
from z3c.relationfield.schema import RelationChoice
from plone.namedfile.interfaces import IImageScaleTraversable
from collective.chimpdrill.utils import IMailsnakeConnection
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.us_states import states_list
from collective.salesforce.fundraising.janrain.rpx import SHARE_JS_TEMPLATE
from collective.salesforce.fundraising.personal_campaign_page import IPersonalCampaignPage

import logging
logger = logging.getLogger("Plone")

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

    first_name = schema.TextLine(
        title=u"First Name",
        description=u"The donor's first name as submitted in the donation form",
        required=False,
    )

    last_name = schema.TextLine(
        title=u"Last Name",
        description=u"The donor's last name as submitted in the donation form",
        required=False,
    )

    email = schema.TextLine(
        title=u"Email",
        description=u"The donor's email as submitted in the donation form",
        required=False,
    )

    email_opt_in = schema.TextLine(
        title=u"Email Opt In",
        description=u"The donor's selection for email opt in submitted in the donation form",
        required=False,
    )

    phone = schema.TextLine(
        title=u"Phone",
        description=u"The donor's phone number as submitted in the donation form",
        required=False,
    )

    address_street = schema.TextLine(
        title=u"Street Address",
        description=u"The donor's street address as submitted in the donation form",
        required=False,
    )

    address_city = schema.TextLine(
        title=u"City",
        description=u"The donor's city as submitted in the donation form",
        required=False,
    )

    address_state = schema.TextLine(
        title=u"State",
        description=u"The donor's state as submitted in the donation form",
        required=False,
    )

    address_zip = schema.TextLine(
        title=u"Zip",
        description=u"The donor's zip as submitted in the donation form",
        required=False,
    )

    address_country = schema.TextLine(
        title=u"Country",
        description=u"The donor's country as submitted in the donation form",
        required=False,
    )

    fingerprint = schema.TextLine(
        title=u"Fingerprint",
        description=u"The Stripe card fingerprint",
        required=False,
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

class ISalesforceDonationSync(Interface):
    def sync_to_salesforce():
        """ main method to sync donation to Salesforce.  Returns the salesforce ID for the opportunity """
    def get_products():
        """ get the products from the donation and convert to SF object structure """
    def create_opportunity():
        """ create the opportunity object for this donation in SF """
    def create_products():
        """ create opportunity products if needed """
    def create_opportunity_contact_role():
        """ create the opportunity contact role linking the contact with the opportunity """
    def create_campaign_member():
        """ create a campaign member object linking the contact to the campaign """

class IDonationReceipt(Interface):
    def render_html():
        """ render the receipt as html """

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

    def get_friendly_date(self):
        return self.created().strftime('%B %d, %Y %I:%S%p %Z')

    def get_chimpdrill_campaign_data(self):
        page = self.get_fundraising_campaign_page()
        return page.get_chimpdrill_campaign_data()

    def get_chimpdrill_thank_you_data(self, request):
        receipt_view = None
        receipt = None
        receipt_view = getMultiAdapter((self, request), name='receipt')
        receipt_view.set_donation_key(self.secret_key)
        receipt = receipt_view()

        campaign = self.get_fundraising_campaign_page()
        campaign_thank_you = None
        if campaign.thank_you_message:
            campaign_thank_you = campaign.thank_you_message.output

        data = {
            'merge_vars': [
                {'name': 'first_name', 'content': self.first_name},
                {'name': 'last_name', 'content': self.last_name},
                {'name': 'amount', 'content': self.amount},
            ],
            'blocks': [
                {'name': 'receipt', 'content': receipt},
                {'name': 'campaign_thank_you', 'content': campaign_thank_you},
            ],
        }

        campaign_data = self.get_chimpdrill_campaign_data()
        data['merge_vars'].extend(campaign_data['merge_vars'])
        data['blocks'].extend(campaign_data['blocks'])

        return data

    def get_chimpdrill_honorary_data(self):
        # Use default values if none provided, useful for preview rendering
        honorary_first_name = self.honorary_first_name
        if not honorary_first_name:
            honorary_first_name = "FIRST_NAME"

        honorary_last_name = self.honorary_last_name
        if not honorary_last_name:
            honorary_last_name = "LAST_NAME"

        honorary_recipient_first_name = self.honorary_recipient_first_name
        if not honorary_recipient_first_name:
            honorary_recipient_first_name = "FIRST_NAME"

        honorary_recipient_last_name = self.honorary_recipient_last_name
        if not honorary_recipient_last_name:
            honorary_recipient_last_name = "LAST_NAME"
        
        data = {
            'merge_vars': [
                {'name': 'donor_first_name', 'content': self.first_name},
                {'name': 'donor_last_name', 'content': self.last_name},
                {'name': 'honorary_first_name', 'content': honorary_first_name},
                {'name': 'honorary_last_name', 'content': honorary_last_name},
                {'name': 'honorary_recipient_first_name', 'content': honorary_recipient_first_name},
                {'name': 'honorary_recipient_last_name', 'content': honorary_recipient_last_name},
                {'name': 'honorary_email', 'content': self.honorary_email},
                {'name': 'honorary_message', 'content': self.honorary_message},
            ],
            'blocks': [],
        }

        campaign_data = self.get_chimpdrill_campaign_data()
        data['merge_vars'].extend(campaign_data['merge_vars'])
        data['blocks'].extend(campaign_data['blocks'])

        return data

    def get_chimpdrill_personal_page_donation_data(self):
        data = {
            'merge_vars': [
                {'name': 'amount', 'content': self.amount},
                {'name': 'donor_first_name', 'content': self.first_name},
                {'name': 'donor_last_name', 'content': self.last_name},
                {'name': 'donor_email', 'content': self.email},
            ],
            'blocks': [],
        }
        
        campaign_data = self.get_chimpdrill_campaign_data()
        data['merge_vars'].extend(campaign_data['merge_vars'])
        data['blocks'].extend(campaign_data['blocks'])

        return data

    def send_chimpdrill_thank_you(self, request, template):
        mail_to = self.email
        data = self.get_chimpdrill_thank_you_data(request)

        return template.send(email = mail_to,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

    def render_chimpdrill_thank_you(self, request, template):
        data = self.get_chimpdrill_thank_you_data(request)

        return template.render(
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

    def send_chimpdrill_honorary(self, template):
        if not self.honorary_email:
            # Skip if we have no email to send to
            return

        mail_to = self.honorary_email
        data = self.get_chimpdrill_honorary_data()

        template.send(email = mail_to,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

        template.send(email = self.email,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )
            
        
    def render_chimpdrill_honorary(self, template):
        data = self.get_chimpdrill_honorary_data()

        return template.render(
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )


    def send_chimpdrill_memorial(self, template):
        if not self.honorary_email:
            # Skip if we have no email to send to
            return

        mail_to = self.honorary_email
        data = self.get_chimpdrill_honorary_data()

        template.send(email = mail_to,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

        template.send(email = self.email,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

        
    def render_chimpdrill_memorial(self, template):
        data = self.get_chimpdrill_honorary_data()

        return template.render(
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

    def render_chimpdrill_personal_page_donation(self, template):
        data = self.get_chimpdrill_personal_page_donation_data()

        return template.render(
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

    def send_chimpdrill_personal_page_donation(self, template):
        page = self.get_fundraising_campaign_page()
        if not page.is_personal():
            # Skip if the donation was not to a personal campaign page
            return

        person = page.get_fundraiser()
        if not person:
            return
        if not person.email:
            return

        mail_to = person.email
        data = self.get_chimpdrill_personal_page_donation_data()

        return template.send(email = mail_to,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

    def send_donation_receipt(self, request, key):
        settings = get_settings()

        # If configured, send a Mandrill template via collective.chimpdrill
        campaign = self.get_fundraising_campaign()
        uuid = getattr(campaign, 'chimpdrill_template_thank_you', None)
        if uuid:
            template = uuidToObject(uuid)
            return self.send_chimpdrill_thank_you(request, template)

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
        mail_to = self.email

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
            self.donor_quote_form.widgets.get('name').value = u'%s %s' % (self.context.first_name, self.context.last_name)
            #self.donor_quote_form.widgets.get('contact_sf_id').value = unicode(self.receipt_view.person.sf_object_id)
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

        campaign = self.context.get_fundraising_campaign_page()
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

    def send_email(self):

        # If a chimpdrill template is configured for this campaign, use it to send the email
        campaign = self.context.get_fundraising_campaign()
        if self.context.honorary_type == 'memorial':
            template_uid = getattr(campaign, 'chimpdrill_template_memorial')
            if template_uid:
                template = uuidToObject(template_uid)
                if template:
                    return self.context.send_chimpdrill_memorial(template)
        else:
            template_uid = getattr(campaign, 'chimpdrill_template_honorary')
            if template_uid:
                template = uuidToObject(template_uid)
                if template:
                    return self.context.send_chimpdrill_honorary(template)

        
        settings = get_settings() 

#        # Construct the email bodies
#        pt = getToolByName(self.context, 'portal_transforms')
#        if self.context.honorary_type == u'Honorary':
#            email_view = getMultiAdapter((self.context, self.request), name='honorary-email')
#        else:
#            email_view = getMultiAdapter((self.context, self.request), name='memorial-email')
#
#        email_body = email_view()
#
#        txt_body = pt.convertTo('text/-x-web-intelligent', email_body, mimetype='text/html')
#
#        # Construct the email message                
#        portal_url = getToolByName(self.context, 'portal_url')
#        portal = portal_url.getPortalObject()
#
#        mail_from = '"%s" <%s>' % (portal.getProperty('email_from_name'), portal.getProperty('email_from_address'))
#        mail_cc = self.context.email
#
#        msg = MIMEMultipart('alternative')
#        subject_vars = {'first_name': self.context.honorary_first_name, 'last_name': self.context.honorary_last_name}
#        if self.context.honorary_type == 'Memorial': 
#                msg['Subject'] = 'Gift received in memory of %(first_name)s %(last_name)s' % subject_vars
#        else:
#            msg['Subject'] = 'Gift received in honor of %(first_name)s %(last_name)s' % subject_vars
#        msg['From'] = mail_from
#        msg['To'] = self.context.honorary_email
#        if mail_cc:
#            msg['Cc'] = mail_cc
#
#        part1 = MIMEText(txt_body, 'plain')
#        part2 = MIMEText(email_body, 'html')
#
#        msg.attach(part1)
#        msg.attach(part2)
#
#        # Attempt to send it
#        try:
#
#            # Send the notification email
#            host = getToolByName(self, 'MailHost')
#            host.send(msg, immediate=True)
#
#        except smtplib.SMTPRecipientsRefused:
#            # fail silently so errors here don't freak out the donor about their transaction which was successful by this point
#            pass


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
                self.send_email()

            # Redirect on to the thank you page
            self.request.response.redirect('%s?key=%s' % (self.context.absolute_url(), self.context.secret_key))

        self.countries = CountryAvailability().getCountryListing()
        self.countries.sort()

        self.states = states_list

        return self.form_template()

class DonationReceipt(grok.Adapter):
    grok.provides(IDonationReceipt)
    grok.context(IDonation)

    render = ViewPageTemplateFile('donation_templates/receipt.pt')

    def update(self):
        settings = get_settings()
        self.organization_name = settings.organization_name
        self.donation_receipt_legal = settings.donation_receipt_legal
        if getattr(self.context, 'donation_receipt_legal', None):
            self.donation_receipt_legal = self.context.donation_receipt_legal

        self.products = []
        if self.context.products:
            for product in self.context.products:
                price, quantity, product_uuid = product.split('|', 2)
                total = int(price) * int(quantity)
                product = uuidToObject(product_uuid)
                if not product:
                    continue
                if product.donation_only:
                    price = total
                    quantity = '-'
                self.products.append({
                    'price': price,
                    'quantity': quantity,
                    'product': product,
                    'total': total,
                })

        self.campaign = self.context.get_fundraising_campaign()
        self.page = self.context.get_fundraising_campaign_page()
        self.is_personal = self.page.is_personal()
    

class DonationReceiptView(grok.View):
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

        self.products = []
        if self.context.products:
            for product in self.context.products:
                price, quantity, product_uuid = product.split('|', 2)
                total = int(price) * int(quantity)
                product = uuidToObject(product_uuid)
                if not product:
                    continue
                if product.donation_only:
                    price = total
                    quantity = '-'
                self.products.append({
                    'price': price,
                    'quantity': quantity,
                    'product': product,
                    'total': total,
                })

        self.campaign = self.context.get_fundraising_campaign()
        self.page = self.context.get_fundraising_campaign_page()
        self.is_personal = False
        if IPersonalCampaignPage.providedBy(self.page):
            self.is_personal = True

    def set_donation_key(self, key=None):
        self.key = self.request.form.get('key', key)


class ThankYouEmail(grok.View):
    grok.context(IDonation)
    grok.require('zope2.View')
    
    grok.name('thank-you-email')
    email_template = ViewPageTemplateFile('donation_templates/thank-you-email.pt')
    
    def render(self):
        # If the fundraising campaign has a chimpdrill_template_thank_you configured,
        # render the template rather than using the built in view
        campaign = self.context.get_fundraising_campaign()
        template_uid = getattr(campaign, 'chimpdrill_template_thank_you')
        if template_uid:
            template = uuidToObject(template_uid)
            if template:
                return self.context.render_chimpdrill_thank_you(self.request, template)

        return self.email_template()
    
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
    email_template = ViewPageTemplateFile('donation_templates/honorary-email.pt')

    def render(self):
        # If the fundraising campaign has a chimpdrill_template_honorary configured,
        # render the template rather than using the built in view
        campaign = self.context.get_fundraising_campaign()
        template_uid = getattr(campaign, 'chimpdrill_template_honorary')
        if template_uid:
            template = uuidToObject(template_uid)
            if template:
                return self.context.render_chimpdrill_honorary(template)

        return self.email_template()
    
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
    email_template = ViewPageTemplateFile('donation_templates/memorial-email.pt')

    def render(self):
        # If the fundraising campaign has a chimpdrill_template_memorial configured,
        # render the template rather than using the built in view
        campaign = self.context.get_fundraising_campaign()
        template_uid = getattr(campaign, 'chimpdrill_template_memorial')
        if template_uid:
            template = uuidToObject(template_uid)
            if template:
                return self.context.render_chimpdrill_memorial(template)

        return self.email_template()
    
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



class SalesforceSyncView(grok.View):
    grok.context(IDonation)
    grok.require('zope2.View')
    grok.name('sync_to_salesforce')

    def render(self):
        async = getUtility(IAsyncService)
        async.queueJob(async_salesforce_sync, self.context)
        return 'OK: Queued for sync'

    def update(self):
        key = getattr(self, 'key', None)
        if not key:
            self.set_donation_key()
            key = getattr(self, 'key', None)

        if not key or key != self.context.secret_key:
            raise Unauthorized

    def set_donation_key(self, key=None):
        # Do nothing if already set
        if getattr(self, 'key', None):
            return

        self.key = self.request.form.get('key', key)

class SalesforceDonationSync(grok.Adapter):
    grok.provides(ISalesforceDonationSync)
    grok.context(IDonation)

    def sync_to_salesforce(self):
        # Check if the sync has already been run, return object id if so
        sf_object_id = getattr(aq_base(self.context), 'sf_object_id', None)
        if sf_object_id:
            return sf_object_id
      
        self.person = self.context.person
        if self.person:
            self.person = self.person.to_object

        # Skip if there is no person set on the donation.  This means the 
        # syncDonationPerson hasn't yet run successfully and we need the person
        # to get their contact id
        if self.person is None:
            return

        self.sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
        self.campaign = self.context.get_fundraising_campaign_page()
        self.pricebook_id = None
        self.settings = get_settings()

        self.get_products()
        self.create_opportunity()
        self.create_products()
        self.create_opportunity_contact_role()
        self.create_campaign_member()
        
        return self.context.sf_object_id

    def get_products(self):
        self.products = []
        self.product_objs = {}

        if not self.context.products:
            return

        for line_item in self.context.products:
            price, quantity, product_uuid = line_item.split('|', 2)
            product = uuidToObject(product_uuid)
            self.products.append({
                'type': 'OpportunityLineItem',
                'PricebookEntryId': product.pricebook_entry_sf_id,
                'UnitPrice': price,
                'Quantity': quantity,
            })
            self.product_objs[product.pricebook_entry_sf_id] = product

    def create_opportunity(self):
        # Create the Opportunity object and Opportunity Contact Role (2 API calls)
        data = {
            'type': 'Opportunity',
            'AccountId': self.settings.sf_individual_account_id,
            'Success_Transaction_Id__c': self.context.transaction_id,
            'Amount': self.context.amount,
            'Name': '%s %s - $%i One Time Donation' % (self.person.first_name, self.person.last_name, self.context.amount),
            'StageName': 'Posted',
            'CloseDate': datetime.now(),
            'CampaignId': self.campaign.sf_object_id,
            'Source_Campaign__c': self.context.source_campaign_sf_id,
            'Source_Url__c': self.context.source_url,
        }

        if self.products:
       
            products_configured = False 
            for product in self.products:
                product_obj = self.product_objs.get(product['PricebookEntryId'])
                parent_form = product_obj.get_parent_product_form()
                if not products_configured:
                    if parent_form:
                        data['Name'] = '%s %s - %s' % (self.person.first_name, self.person.last_name, parent_form.title)
                    else:
                        product_obj = self.product_objs.get(product['PricebookEntryId'])
                        data['Name'] = '%s %s - %s (Qty %s)' % (self.person.first_name, self.person.last_name, product_obj.title, product['Quantity'])

                    if self.settings.sf_opportunity_record_type_product:
                        data['RecordTypeID'] = self.settings.sf_opportunity_record_type_product

                    # Set the pricebook on the Opportunity to the standard pricebook
                    data['Pricebook2Id'] = self.pricebook_id
        
                    # Set amount to 0 since the amount is incremented automatically by Salesforce
                    # when an OpportunityLineItem is created against the Opportunity
                    data['Amount'] = 0
        
                    products_configured = True

        else:
            # this is a one-time donation, record it as such if possible
            if self.settings.sf_opportunity_record_type_one_time:
                data['RecordTypeID'] = self.settings.sf_opportunity_record_type_one_time

        res = self.sfbc.create(data)

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        self.opportunity = res[0]
        self.context.sf_object_id = self.opportunity['id']
        self.context.reindexObject()

    def create_products(self):
        if not self.products:
            return
        products = []
        for product in self.products:
            product['OpportunityId'] = self.opportunity['id']
            products.append(product)
        res = self.sfbc.create(products)

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

    def create_opportunity_contact_role(self):
        res = self.sfbc.create({ 'type': 'OpportunityContactRole',
            'OpportunityId': self.opportunity['id'],
            'ContactId': self.person.sf_object_id,
            'IsPrimary': True,
            'Role': 'Decision Maker',
        })

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

    def create_campaign_member(self):
        # Create the Campaign Member (1 API Call).  Note, we ignore errors on this step since
        # trying to add someone to a campaign that they're already a member of throws
        # an error.  We want to let people donate more than once.
        # Ignoring the error saves an API call to first check if the member exists
        if self.settings.sf_create_campaign_member:
            res = self.sfbc.create({
                'type': 'CampaignMember',
                'CampaignId': self.campaign.sf_object_id,
                'ContactId': self.person.sf_object_id,
                'Status': 'Responded',
            })

@grok.subscribe(IDonation, IObjectAddedEvent)
def queueSyncDonationPerson(donation, event):
    async = getUtility(IAsyncService)
    async.queueJob(syncDonationPerson, donation)


def syncDonationPerson(donation):
    if donation.person:
        return        

    person = None

    mt = getToolByName(donation, 'membrane_tool')
    pm = getToolByName(donation, 'portal_membership')
    res = mt.searchResults(getUserName = donation.email)
    if res:
        person = res[0].getObject()

    # If no existing user, create one which creates the contact in SF (1 API call)
    if not res:
        data = {
            'first_name': donation.first_name,
            'last_name': donation.last_name,
            'email': donation.email,
            'phone': donation.phone,
            'address': donation.address_street,
            'city': donation.address_city,
            'state': donation.address_state,
            'zip': donation.address_zip,
            'country': donation.address_country,
        }

        # Treat the email_opt_in field as a ratchet.  Once toggled on, it stays on even if unchecked
        # on a subsequent donation.  Unsubscribing is the way to prevent emails once opted in.
        if donation.email_opt_in:
            data['email_opt_in'] = donation.email_opt_in

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
        mtool = getToolByName(donation, 'portal_membership')
        acl = getToolByName(donation, 'acl_users')
        #newSecurityManager(None, acl.getUser(donation.email))
        #mtool.loginUser()

        # See if any values are modified and if so, update the Person and upsert the changes to SF
        person = res[0].getObject()
        old_data = [person.address, person.city, person.state, person.zip, person.country, person.phone]
        new_data = [donation.address_street, donation.address_city, donation.address_state, donation.address_zip, donation.address_country, donation.phone]

        if new_data != old_data:
            person.address = donation.address_street
            person.city = donation.address_city
            person.state = donation.address_state
            person.zip = donation.address_zip
            person.country = donation.address_country
            person.phone = donation.phone
            person.reindexObject()

            person.upsertToSalesforce()

        #mtool.logoutUser()

    # Set the person field on the campaign
    intids = getUtility(IIntIds)
    person_intid = intids.getId(person)
    donation.person = RelationValue(person_intid)
    person.upsertToSalesforce()

    # Skipping event since we don't want to queue the update, we need to run it now
    event = ObjectModifiedEvent(donation)
    notify(event)


def async_salesforce_sync(donation):
    return ISalesforceDonationSync(donation).sync_to_salesforce()

@grok.subscribe(IDonation, IObjectAddedEvent)
def queueSalesforceSync(donation, event):
    async = getUtility(IAsyncService)
    async.queueJob(async_salesforce_sync, donation)

# FIXME: can't be async for now since receipt requires request
#@grok.subscribe(IDonation, IObjectAddedEvent)
#def queueDonationReceipt(donation, event):
#    async = getUtility(IAsyncService)
#    receipt_html = donation.get_receipt_html()
#    async.queueJob(async_salesforce_sync, donation, receipt_html)
#
#def sendDonationReceipt(donation, receipt_html):
#    pass

def mailchimpSubscribeDonor(donation):
    campaign = donation.get_fundraising_campaign()

    merge_vars = {
        'FNAME': donation.first_name,
        'LNAME': donation.last_name,
        'L_AMOUNT': donation.amount,
        'L_DATE': donation.get_friendly_date(),
        'L_RECEIPT': '%s?key=%s' % (donation.absolute_url(), donation.secret_key),
    }
    mc = getUtility(IMailsnakeConnection).get_mailchimp()
    return mc.listSubscribe(
        id = campaign.chimpdrill_list_donors,
        email_address = donation.email,
        merge_vars = merge_vars,
        update_existing = True,
        double_optin = False,
        send_welcome = False,
    )

@grok.subscribe(IDonation, IObjectModifiedEvent)
def queueMailchimpSubscribeDonor(donation, event):
    campaign = donation.get_fundraising_campaign()
    if not campaign.chimpdrill_list_donors:
        return 'Skipping, no donors list specified for campaign'

    async = getUtility(IAsyncService)
    async.queueJob(mailchimpSubscribeDonor, donation)


#@grok.subscribe(IDonation, IObjectAddedEvent)
#def mailchimpUpdateFundraiserVars(donation, event):
    #return

def mailchimpSendPersonalCampaignDonation(donation):
    campaign = donation.get_fundraising_campaign()
    uuid = getattr(campaign, 'chimpdrill_template_personal_page_donation', None)
    if uuid:
        template = uuidToObject(uuid)
        return donation.send_chimpdrill_personal_page_donation(template)

@grok.subscribe(IDonation, IObjectModifiedEvent)
def queueMailchimpSendPersonalCampaignDonation(donation, event):
    page = donation.get_fundraising_campaign_page()
    if not page.is_personal():
        # Skip if not a personal page
        return 'Skipping, not a personal page'

    async = getUtility(IAsyncService)
    async.queueJob(mailchimpSendPersonalCampaignDonation, donation)


import random
import string
from five import grok
from zope import schema
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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

    def get_friendly_date(self):
        return self.created().strftime('%B %d, %Y %I:%S%p %Z')

    def get_chimpdrill_campaign_data(self):
        campaign = self.get_fundraising_campaign()
        campaign_image_url = None

        if campaign.image and campaign.image.filename:
            campaign_image_url = '%s/@@images/image' % campaign.absolute_url()

        return {
            'merge_vars': [
                {'name': 'campaign_name', 'content': campaign.title},
                {'name': 'campaign_url', 'content': campaign.absolute_url()},
                {'name': 'campaign_image_url', 'content': campaign_image_url},
                {'name': 'campaign_header_image_url', 'content': campaign.get_header_image_url()},
            ],
            'blocks': [],
        }

    def get_chimpdrill_thank_you_data(self, request):
        if not self.person or not self.person.to_object:
            # Skip if we have no email to send to
            return
        person = self.person.to_object

        receipt_view = None
        receipt = None
        receipt_view = getMultiAdapter((self, request), name='receipt')
        receipt_view.set_donation_key(self.secret_key)
        receipt = receipt_view()

        campaign = self.get_fundraising_campaign()
        campaign_thank_you = None
        if campaign.thank_you_message:
            campaign_thank_you = campaign.thank_you_message.output

        data = {
            'merge_vars': [
                {'name': 'first_name', 'content': person.first_name},
                {'name': 'last_name', 'content': person.last_name},
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
        person = self.person.to_object

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
                {'name': 'donor_first_name', 'content': person.first_name},
                {'name': 'donor_last_name', 'content': person.last_name},
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

    def send_chimpdrill_thank_you(self, request, template):
        if not self.person or not self.person.to_object:
            # Skip if we have no email to send to
            return

        mail_to = self.person.to_object.email
        data = self.get_chimpdrill_thank_you_data(request)

        return template.send(email = mail_to,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

    def render_chimpdrill_thank_you(self, template):
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

        return template.send(email = mail_to,
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

        return template.send(email = mail_to,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )
        
    def render_chimpdrill_memorial(self, template):
        data = self.get_chimpdrill_honorary_data()

        return template.render(
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )


    def send_donation_receipt(self, request, key):
        settings = get_settings()

        # If configured, send a Mandrill template via collective.chimpdrill
        # FIXME: will this work in a personal campaign?
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
        if not self.person or not self.person.to_object:
            # Skip if we have no email to send to
            return
        mail_to = self.person.to_object.email

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
                return self.context.render_chimpdrill_thank_you(template)

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


class SalesforceSync(grok.View):
    grok.context(IDonation)
    grok.name('sync_to_salesforce')
    grok.require('zope2.View')

    def render(self):
        key = getattr(self, 'key', None)
        if not key:
            self.set_donation_key()
            key = getattr(self, 'key', None)

        if not key or key != self.context.secret_key:
            raise Unauthorized

        # Check if the sync has already been run, raise exception if so
        if self.context.sf_object_id:
            raise Exception('This donation has already been created in Salesforce')
      
        self.person = self.context.person
        if self.person:
            self.person = self.person.to_object
        self.sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
        self.campaign = self.get_fundraising_campaign()
        self.pricebook_id = None
        self.settings = get_settings()

        self.get_products()
        self.sync_person()
        self.create_opportunity()
        self.create_products()
        self.create_opportunity_contact_role()
        self.create_campaign_member()

    def set_donation_key(self, key=None):
        # Do nothing if already set
        if getattr(self, 'key', None):
            return

        self.key = self.request.form.get('key', key)

    def get_products(self):
        self.products = []

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

    def sync_contact(self):
        # Nothing to do here since the person should already be synced
        if self.context.person and self.context.person.to_object:
            self.contact_sf_id = self.person.to_object.sf_object_id

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
            'Source_Campaign__c': self.campaign.get_source_campaign(),
            'Source_Url__c': self.campaign.get_source_url(),
        }

        if product_id and product is not None:
            # FIXME: Add custom record type for Stripe Donations
            # record product donations as a particular type, if possible
            if self.settings.sf_opportunity_record_type_product:
                data['RecordTypeID'] = self.settings.sf_opportunity_record_type_product
            # Set the pricebook on the Opportunity to the standard pricebook
            data['Pricebook2Id'] = self.pricebook_id

            # Set amount to 0 since the amount is incremented automatically by Salesforce
            # when an OpportunityLineItem is created against the Opportunity
            data['Amount'] = 0

            # Set a custom name with the product info and quantity
            data['Name'] = '%s %s - %s (Qty %s)' % (self.person.first_name, self.person.last_name, product.title, quantity)

        elif products:
            # record product donations as a particular type, if possible
            if self.settings.sf_opportunity_record_type_product:
                data['RecordTypeID'] = self.settings.sf_opportunity_record_type_product
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
            if self.settings.sf_opportunity_record_type_one_time:
                data['RecordTypeID'] = self.settings.sf_opportunity_record_type_one_time


        res = sfbc.create(data)

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        self.opportunity = res

    def create_products(self):
        if not self.products:
            return
        products = []
        for product in self.products:
            product['OpportunityId'] = self.opportunity['id']
        res = sfbc.create(products)

        if not role_res[0]['success']:
            raise Exception(role_res[0]['errors'][0]['message'])

    def create_opportunity_contact_role(self):
        role_res = sfbc.create({ 'type': 'OpportunityContactRole',
            'OpportunityId': self.opportunity['id'],
            'ContactId': self.person.sf_object_id,
            'IsPrimary': True,
            'Role': 'Decision Maker',
        })

        if not role_res[0]['success']:
            raise Exception(role_res[0]['errors'][0]['message'])

    def create_campaign_member(self):
        # Create the Campaign Member (1 API Call).  Note, we ignore errors on this step since
        # trying to add someone to a campaign that they're already a member of throws
        # an error.  We want to let people donate more than once.
        # Ignoring the error saves an API call to first check if the member exists
        if self.settings.sf_create_campaign_member:
            role_res = sfbc.create({
                'type': 'CampaignMember',
                'CampaignId': campaign.sf_object_id,
                'ContactId': person.sf_object_id,
                'Status': 'Responded',
            })

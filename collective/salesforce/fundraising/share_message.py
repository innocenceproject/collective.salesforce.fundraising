import re
from five import grok
from zope.interface import alsoProvides
from zope import schema
from zope.component import getUtility
from zope.app.content.interfaces import IContentType
from plone.directives import dexterity, form
from plone.supermodel import model
from z3c.form import button
from zope.app.container.interfaces import IObjectAddedEvent
from Products.CMFCore.utils import getToolByName
from zope.component.hooks import getSite
from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from Products.statusmessages.interfaces import IStatusMessage
from plone.namedfile.interfaces import IImageScaleTraversable
from plone.namedfile.field import NamedBlobImage
from Products.validation.validators.BaseValidators import EMAIL_RE
from collective.simplesalesforce.utils import ISalesforceUtility
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.janrain.rpx import SHARE_JS_TEMPLATE


# Interface class; used to define content-type schema.

class IShareMessage(model.Schema, IImageScaleTraversable):
    """
    A message to be shared on social networks
    """

    image = NamedBlobImage(
        title=u"Image",
        description=u"Image used in the share message",
    )

    model.load("models/share_message.xml")
alsoProvides(IShareMessage, IContentType)

class ShareMessage(dexterity.Item):
    grok.implements(IShareMessage)

    def get_container(self):
        if not self.parent_sf_id:
            return None
        site = getSite()
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(
            sf_object_id=self.parent_sf_id, 
            portal_type = ['collective.salesforce.fundraising.fundraisingcampaign','collective.salesforce.fundraising.personalcampaignpage'],
        )
        if not res:
            return None
        return res[0].getObject()

# Add to Salesforce on creation
@grok.subscribe(IShareMessage, IObjectAddedEvent)
def createSalesforceCampaign(message, event):
    # Set the parent_sf_id using the parent
    if not message.parent_sf_id:
        message.parent_sf_id = message.aq_parent.sf_object_id

    # create Share Message campaign in Salesforce
    site = getSite()
    sfconn = getUtility(ISalesforceUtility).get_connection()
    data = {
        'Type': 'Share Message',
        'Name': message.title,
        'Public_Name__c': message.title,
        'Status': message.status,
        'ParentId': message.parent_sf_id,
    }
    settings = get_settings()

    if settings.sf_campaign_record_type_share:
        data['RecordTypeId'] = settings.sf_campaign_record_type_share

    res = sfconn.Campaign.create(data)
    if not res['success']:
        raise Exception(res['errors'][0])

    message.sf_object_id = res['id']

class JanrainView(grok.View):
    grok.context(IShareMessage)
    grok.require('zope2.View')
    grok.name('view')

    def update(self):
        self.link_id = 'share-message-' + self.context.id
        if not hasattr(self, 'url'):
            self.set_url()
        self.show_email_share = get_settings().enable_share_via_email
        comment = self.context.comment
        if comment:
            comment = comment.replace("'","\\'")
        self.message_js = SHARE_JS_TEMPLATE % {
            'link_id': self.link_id,
            'url': self.url,
            'title': self.context.title.replace("'","\\'"),
            'description': self.context.description.replace("'","\\'"),
            'image': self.context.absolute_url() + '/@@images/image',
            'message': comment,
        }

    def set_url(self, url=None):
        if url:
            if url.find('?source_campaign=') == -1:
                url = url + '?source_campaign=' + self.context.sf_object_id
            self.url = url
        else:
            self.url = self.context.aq_parent.absolute_url() + '?source_campaign=' + self.context.sf_object_id
        self.url = self.url.replace("'","\\'")
        


class InvalidEmailError(schema.ValidationError):
    __doc__ = u'Please enter a valid e-mail address.'
def isEmail(value):
    if re.match('^'+EMAIL_RE, value):
        return True
    raise InvalidEmailError


class IEmailMessage(form.Schema):

    mfrom = schema.ASCIILine(title=_(u'From'))
    form.mode(mfrom='display')

    mto = schema.ASCIILine(
        title=_(u'To'),
        description=_(u'Enter an email address'),
        constraint=isEmail)
    subject = schema.TextLine(title=_(u'Subject'))
    body = schema.Text(
        title=_(u'Message body'),
        description=_(u'Be sure to add a note and signature to personalize your message.')
        )


class EmailForm(form.SchemaForm):
    grok.context(IShareMessage)
    grok.require('zope2.View')
    grok.name('email')

    label = _(u'Share via email')
    description = _(u'Send a message to ask someone to support your campaign.')
    schema = IEmailMessage
    finished = False

    def getContent(self):
        portal = getToolByName(self.context, 'portal_url').getPortalObject()
        fromaddr = portal.getProperty('email_from_address')
        fromname = portal.getProperty('email_from_name')
        mfrom = '%s <%s>' % (fromname, fromaddr)

        campaign_url = self.context.aq_parent.absolute_url() + '?source_campaign=' + self.context.sf_object_id
        body = "%s\n\n%s\n\n%s" % (self.context.description, self.context.comment, campaign_url)
        return {'mfrom': mfrom, 'subject': self.context.title, 'body': body}

    @button.buttonAndHandler(u'Send email')
    def handleSend(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        mailhost = getToolByName(self.context, 'MailHost')
        mailhost.send(data['body'], data['mto'], self.getContent()['mfrom'],
            subject=data['subject'], charset='utf-8', immediate=True)

        IStatusMessage(self.request).add(u'Your email was successfully sent.')
        self.finished = True

    def render(self):
        if self.finished:
            return '<html></html>'  # return blank so the popup closes
        return super(EmailForm, self).render()

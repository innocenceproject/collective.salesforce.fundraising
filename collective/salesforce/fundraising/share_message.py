import re
from five import grok
from zope.interface import alsoProvides
from zope import schema
from zope.app.content.interfaces import IContentType
from plone.directives import dexterity, form
from z3c.form import button
from zope.app.container.interfaces import IObjectAddedEvent
from Products.CMFCore.utils import getToolByName
from zope.site.hooks import getSite
from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from Products.statusmessages.interfaces import IStatusMessage
from plone.namedfile.interfaces import IImageScaleTraversable
from Products.validation.validators.BaseValidators import EMAIL_RE
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.janrain.rpx import SHARE_JS_TEMPLATE


# Interface class; used to define content-type schema.

class IShareMessage(form.Schema, IImageScaleTraversable):
    """
    A message to be shared on social networks
    """

    form.model("models/share_message.xml")
alsoProvides(IShareMessage, IContentType)

class ShareMessage(dexterity.Item):
    grok.implements(IShareMessage)

    def get_container(self):
        if not self.parent_sf_id:
            return None
        site = getSite()
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(sf_object_id=self.parent_sf_id)
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
    sfbc = getToolByName(site, 'portal_salesforcebaseconnector')
    data = {
        'type': 'Campaign',
        'Type': 'Share Message',
        'Name': message.title,
        'Public_Name__c': message.title,
        'Status': message.status,
        'ParentId': message.parent_sf_id,
    }
    settings = get_settings()

    if settings.sf_campaign_record_type_share:
        data['RecordTypeId'] = settings.sf_campaign_record_type_share

    res = sfbc.create(data)
    if not res[0]['success']:
        raise Exception(res[0]['errors'][0]['message'])

    message.sf_object_id = res[0]['id']

class JanrainView(grok.View):
    grok.context(IShareMessage)
    grok.require('zope2.View')
    grok.name('view')

    def update(self):
        self.link_id = 'share-message-' + self.context.id
        url = self.context.aq_parent.absolute_url() + '?source_campaign=' + self.context.sf_object_id
        url = url.replace("'","\\'")
        self.show_email_share = get_settings().enable_share_via_email
        comment = self.context.comment
        if comment:
            comment = comment.replace("'","\\'")
        self.message_js = SHARE_JS_TEMPLATE % {
            'link_id': self.link_id,
            'url': url,
            'title': self.context.title.replace("'","\\'"),
            'description': self.context.description.replace("'","\\'"),
            'image': self.context.absolute_url() + '/@@images/image',
            'message': comment,
        }


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

from five import grok
from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType
from plone.directives import dexterity, form
from zope.app.container.interfaces import IObjectAddedEvent
from Products.CMFCore.utils import getToolByName
from zope.site.hooks import getSite

from plone.namedfile.interfaces import IImageScaleTraversable


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
    if not message.parent_sf_id:
        message.parent_sf_id = message.aq_parent.sf_object_id

    # create Share Message campaign in Salesforce
    site = getSite()
    sfbc = getToolByName(site, 'portal_salesforcebaseconnector')
    res = sfbc.create({
        'type': 'Campaign',
        'Type': 'Share Message',
        'Name': message.title,
        'Public_Name__c': message.title,
        'Status': message.status,
        'ParentId': message.parent_sf_id,
    })
    if not res[0]['success']:
        raise Exception(res[0]['errors'][0]['message'])

    message.sf_object_id = res[0]['id']


class JanrainView(grok.View):
    grok.context(IShareMessage)
    grok.require('zope2.View')
    grok.name('view')

    def update(self):
        self.message_js = "rpxShareButton(jQuery('#message-%s'), '%s', '%s', '%s', '%s', '%s', '%s');" % (
            self.context.id,
            'Share this message',
            self.context.description,
            self.context.aq_parent.absolute_url() + '?source_campaign=' + self.context.sf_object_id,
            self.context.title,
            self.context.comment,
            self.context.absolute_url() + '/@@images/image',
        )



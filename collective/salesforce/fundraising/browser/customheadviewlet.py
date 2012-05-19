from zope.interface import Interface
from zope.component import getUtility
from five import grok
from plone.app.layout.viewlets.interfaces import IHtmlHead
from plone.registry.interfaces import IRegistry
from collective.salesforce.fundraising.controlpanel.interfaces import IFundraisingSettings
from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage

class CustomFormHeadViewlet(grok.Viewlet):
    """ Render the Custom Form Head field from the Salesforce Fundraising control panel """
   
    grok.name('collective.salesforce.fundraising.customheadviewlet.CustomFormHeadViewlet')
    grok.require('zope2.View')
    grok.context(IFundraisingCampaignPage)
    grok.viewletmanager(IHtmlHead)

    def render(self):
        # Get the site id and app_id from registry
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFundraisingSettings)
        if settings.custom_form_head:
            return settings.custom_form_head
        return ''

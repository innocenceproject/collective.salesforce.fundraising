from five import grok
from plone.app.layout.viewlets.interfaces import IHtmlHead
from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from collective.salesforce.fundraising.utils import get_settings


class CustomFormHeadViewlet(grok.Viewlet):
    """ Render the Custom Form Head field from the Salesforce Fundraising control panel """
   
    grok.name('collective.salesforce.fundraising.customheadviewlet.CustomFormHeadViewlet')
    grok.require('zope2.View')
    grok.context(IFundraisingCampaignPage)
    grok.viewletmanager(IHtmlHead)

    def render(self):
        # Get the site id and app_id from registry
        settings = get_settings()
        if settings.custom_form_head:
            return settings.custom_form_head
        return ''

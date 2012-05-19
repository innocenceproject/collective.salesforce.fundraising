from zope.interface import Interface
from zope.component import getUtility
from five import grok
from plone.app.layout.viewlets.interfaces import IBelowContent
from plone.app.layout.viewlets.interfaces import IHtmlHead
from plone.registry.interfaces import IRegistry
from collective.salesforce.fundraising.controlpanel.interfaces import IFundraisingSettings
from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from collective.salesforce.fundraising.fundraising_campaign import IHideDonationForm

class DonationFormViewlet(grok.Viewlet):
    """ Render the embed code for the donation form """
   
    grok.name('collective.salesforce.fundraising.customheadviewlet.DonationFormViewlet')
    grok.require('zope2.View')
    grok.context(IFundraisingCampaignPage)
    grok.viewletmanager(IBelowContent)

    def render(self):
        if IHideDonationForm.implementedBy(self.view.__class__):
            return ''
        return '<div class="campaign-donate-form">%s</div>' % self.context.populate_form_embed()

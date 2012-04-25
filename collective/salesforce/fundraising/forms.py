from five import grok
from plone.directives import form

from z3c.form import button, field
from Products.CMFCore.interfaces import ISiteRoot

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign
from collective.salesforce.fundraising.personal_campaign_page import IPersonalCampaignPage

from collective.salesforce.fundraising import MessageFactory as _

class CreatePersonalCampaignPageForm(form.Form):
    grok.name('create-personal-campaign-page')
    grok.require('zope2.View')
    grok.context(IFundraisingCampaign)
   
    @property
    def fields(self): 
        return field.Fields(IPersonalCampaignPage).select('goal','personal_appeal')

    ignoreContext = True
    
    label = _(u"Create Personal Campaign Page")
    description = _(u"Set a goal and encourage your friends, family, and colleagues to donate towards your goal.")
    
    @button.buttonAndHandler(_(u'Create'))
    def handleOk(self, action):
        data, errors = self.extractData()
        import pdb; pdb.set_trace()

        if errors:
            self.status = self.formErrorsMessage
            return

        
        
    @button.buttonAndHandler(_(u"Cancel"))
    def handleCancel(self, action):
        return 

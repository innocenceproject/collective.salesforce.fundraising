from plone.app.registry.browser import controlpanel
from collective.salesforce.fundraising.controlpanel.interfaces import IFundraisingSettings, _

class FundraisingSettingsEditForm(controlpanel.RegistryEditForm):

    schema = IFundraisingSettings
    label = _(u"Fundraising settings")
    description = _(u"""""")

    def updateFields(self):
        super(FundraisingSettingsEditForm, self).updateFields()


    def updateWidgets(self):
        super(FundraisingSettingsEditForm, self).updateWidgets()

class FundraisingSettingsControlPanel(controlpanel.ControlPanelFormWrapper):
    form = FundraisingSettingsEditForm

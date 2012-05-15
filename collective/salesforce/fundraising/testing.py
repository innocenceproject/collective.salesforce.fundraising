from plone.testing import z2
from plone.app.testing import PloneSandboxLayer
from plone.app.testing import PLONE_FIXTURE
from plone.app.testing import IntegrationTesting
from plone.app.testing import FunctionalTesting
from Products.salesforcebaseconnector.tests import sfconfig
import transaction


class CollectiveSalesforceFundraisingLayer(PloneSandboxLayer):

    defaultBases = (PLONE_FIXTURE,)

    def setUpZope(self, app, configurationContext):
        import collective.salesforce.fundraising
        self.loadZCML(package=collective.salesforce.fundraising)

        z2.installProduct(app, 'Products.salesforcebaseconnector')

    def setUpPloneSite(self, portal):
        portal.manage_addProduct['salesforcebaseconnector'].manage_addTool('Salesforce Base Connector', None)
        portal.portal_salesforcebaseconnector.setCredentials(sfconfig.USERNAME, sfconfig.PASSWORD)
        self.applyProfile(portal, 'collective.salesforce.fundraising:default')
        transaction.commit()

    def tearDownZope(self, app):
        z2.uninstallProduct(app, 'Products.salesforcebaseconnector')


FIXTURE = CollectiveSalesforceFundraisingLayer()
INTEGRATION_TESTING = IntegrationTesting(bases=(FIXTURE,), name='collective.salesforce.fundraising:Integration')
FUNCTIONAL_TESTING = FunctionalTesting(bases=(FIXTURE,), name='collective.salesforce.fundraising:Functional')

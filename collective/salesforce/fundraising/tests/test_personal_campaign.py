import transaction
import unittest2 as unittest
from collective.salesforce.fundraising.testing import FUNCTIONAL_TESTING
from plone.testing.z2 import Browser
from plone.dexterity.utils import createContentInContainer


class PersonalCampaignFunctionalTest(unittest.TestCase):
    # The layer's setup will run once before all of these tests run,
    # and its teardown will run once after all these tests run.
    layer = FUNCTIONAL_TESTING

    # setUp is run once before *each* of these tests.
    # This stuff can be moved to the layer's setupPloneSite if you want
    # it for all tests using the layer, not just this test class.
    def setUp(self):
        # turn on self registration
        from plone.app.controlpanel.security import ISecuritySchema
        ISecuritySchema(self.layer['portal']).enable_self_reg = True
        # turn off email validation so we can more easily register users
        self.layer['portal'].validate_email = False
        transaction.commit()
        self.ids_to_remove = []

    # tearDown is run once after *each* of these tests.
    # We're using it to remove objects that we recorded as having been
    # added to Salesforce.
    def tearDown(self):
        sfbc = self.layer['portal'].portal_salesforcebaseconnector
        sfbc.delete(self.ids_to_remove)
        self.ids_to_remove = []

    def test_create_personal_campaign(self):
        # create the parent campaign
        portal = self.layer['portal']
        sfbc = portal.portal_salesforcebaseconnector
        res = sfbc.create({'type': 'Campaign', 'Name': 'Test Campaign'})
        campaign_id = res[0]['id']
        self.ids_to_remove.append(campaign_id)
        campaign = createContentInContainer(portal,
            'collective.salesforce.fundraising.fundraisingcampaign', checkConstraints=False,
            title=u'Test Campaign', allow_personal=True, sf_object_id=campaign_id)
        transaction.commit()

        # Now as a normal user, go through the steps in the browser
        browser = Browser(portal)
        browser.open('http://nohost/plone/test-campaign')
        browser.getLink('Create My Campaign').click()
        # We are redirected to log in
        self.assertEqual('http://nohost/plone/acl_users/credentials_cookie_auth/require_login?came_from=http%3A//nohost/plone/test-campaign/%40%40create-or-view-personal-campaign',
            browser.url)

        # Now we need to create a user
        browser.getControl('Full Name').value = 'Harvey Frank'
        browser.getControl('User Name').value = 'harvey'
        browser.getControl('E-mail').value = 'harvey@mailinator.com'
        browser.getControl(name='form.password').value = 'foobar'
        browser.getControl('Confirm password').value = 'foobar'
        browser.getControl('Register').click()
        # We should now be on the personal campaign add form, and logged in.
        self.assertEqual('http://nohost/plone/test-campaign/@@create-personal-campaign-page', browser.url)
        self.assertTrue('Log out' in browser.contents)
        # A contact should have been created in Salesforce, and its id recorded as a member property.
        sf_id = portal.portal_membership.getMemberById('harvey').getProperty('sf_object_id')
        self.assertTrue(sf_id)
        self.ids_to_remove.append(sf_id)

        # Create the personal campaign
        browser.getControl('Title').value = 'My campaign'
        browser.getControl('Goal').value = '42'
        browser.getControl(name='form.widgets.description').value = 'pitch'
        browser.getControl(name='form.widgets.personal_appeal').value = 'Please contribute.'
        browser.getControl(name='form.widgets.thank_you_message').value = 'Thank you'
        browser.handleErrors = False
        browser.getControl('Create').click()

        # Now we should be at the campaign
        self.assertEqual('http://nohost/plone/test-campaign/my-campaign', browser.url)
        # And it should have been created in Salesforce
        personal_campaign_id = getattr(campaign, 'my-campaign').sf_object_id
        self.assertTrue(personal_campaign_id)
        self.ids_to_remove.append(personal_campaign_id)

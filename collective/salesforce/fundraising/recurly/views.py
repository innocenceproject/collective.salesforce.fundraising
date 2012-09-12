from five import grok

from datetime import datetime

from Products.CMFCore.utils import getToolByName

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings

from AccessControl.SecurityManagement import newSecurityManager

from dexterity.membrane.membrane_helpers import get_brains_for_email
from plone.dexterity.utils import createContentInContainer
from zope.app.component.hooks import getSite

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage

import recurly


RECURLY_SUBSCRIBE_JS = """  Recurly.config({
    subdomain: '%(subdomain)s',
    currency: 'USD'
  });

  Recurly.buildSubscriptionForm({
    target: '#recurly-subscribe',
    signature: '%(signature)s',
    successURL: '%(success_url)s',
    afterInject: setupRecurlyForm,
    planCode: '%(plan_code)s',
    collectPhone: true,
    distinguishContactFromBillingInfo: true,
    enableAddOns: false,
    enableCoupons: false,
    collectCompany: false
  });

"""

class DonationFormRecurly(grok.View):
    """ Renders a recurly subscription form for recurring donations """
    #FIXME: return 404 if recurly is not configured
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('donation_form_recurly')
    grok.template('donation_form_recurly')

    def update(self):
        settings = get_settings()

        level_id = self.request.form.get('levels_monthly', None)
        if not level_id:
            level_id = self.request.form.get('levels', settings.default_donation_ask_recurring)
        self.levels = None
        for row in settings.donation_ask_levels:
            row_id, amounts = row.split('|')
            if row_id == level_id:
                self.levels = amounts.split(',')
        if not self.levels:
            self.levels = settings.donation_ask_levels[0].split('|')[1].split(',')

        recurly_subdomain = settings.recurly_subdomain
        self.recurly_js = RECURLY_SUBSCRIBE_JS % {
            'subdomain': recurly_subdomain,   
            'signature': self.generate_signature(),
            'success_url': self.context.absolute_url() + '/post_recurly_subscription',
            'plan_code': settings.recurly_plan_code,
        }

    def generate_signature(self):
        # workaround for http://bugs.python.org/issue5285, map unicode to strings
        settings = get_settings()
        recurly.API_KEY = str(settings.recurly_api_key)
        recurly.js.PRIVATE_KEY = str(settings.recurly_private_key)
        plan_code = str(settings.recurly_plan_code)

        # Set a default currency for your API requests
        recurly.DEFAULT_CURRENCY = 'USD'

        return recurly.js.sign({'subscription': {'plan_code': plan_code}})

class PostRecurlySubscription(grok.View):
    """ Handles the callback from Recurly after a successful subscription creation """
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    
    grok.name('post_recurly_subscription')

    def render(self):
        """ Fetch the subscription details from Recurly and create Salesforce objects.
            Then, redirec the user to the thank you page """

        # SFAPI: Uses 5 calls to register donation in Salesforce, ~2,000 recurring 
        # subscription creations per day with the standard nonprofit 10k calls per day

        token = self.request.form.get('recurly_token')

        if not token:
            return 'ERROR: No token provided'

        # workaround for http://bugs.python.org/issue5285, map unicode to strings
        settings = get_settings()
        recurly.API_KEY = str(settings.recurly_api_key)
        recurly.js.PRIVATE_KEY = str(settings.recurly_private_key)
        # Set a default currency for your API requests
        recurly.DEFAULT_CURRENCY = 'USD'

        sub = recurly.js.fetch(token)
        account = sub.account()
        billing_info = account.billing_info
        email = account.email.lower()

        street_address = billing_info.address1
        if billing_info.address2:
            street_address = '%s\n%s' % (street_address, billing_info.address2)

        # Look for an existing Plone user
        mt = getToolByName(self.context, 'portal_membership')

        res = get_brains_for_email(self.context, email, self.request)
        # If no existing user, create one which creates the contact in SF (1 API call)
        if not res:
            data = {
                'first_name': account.first_name,
                'last_name': account.last_name,
                'email': email,
                'address': street_address,
                'city': billing_info.city,
                'state': billing_info.state,
                'zip': billing_info.zip,
                'country': billing_info.country, 
            }

            # Create the user
            people_container = getattr(getSite(), 'people')
            person = createContentInContainer(
                people_container,
                'collective.salesforce.fundraising.person',
                checkConstraints=False,
                **data
            )

        # If existing user, fill with updated data from subscription profile (1 API call, Person update handler)
        else:
            # Authenticate the user temporarily to fetch their person object with some level of permissions applied
            mtool = getToolByName(self.context, 'portal_membership')
            acl = getToolByName(self.context, 'acl_users')
            newSecurityManager(None, acl.getUser(email))
            mtool.loginUser()

            person = res[0].getObject()

            # See if any values are modified and if so, update the Person and upsert the changes to SF
            person = res[0].getObject()
            old_data = [person.address, person.city, person.state, person.zip, person.country, person.phone]
            new_data = [street_address, billing_info.city, billing_info.state, billing_info.zip, billing_info.country, billing_info.phone]
    
            if new_data != old_data:
                
                person.address = street_address
                person.city = billing_info.city
                person.state = billing_info.state
                person.zip = billing_info.zip
                person.country = billing_info.country
                person.phone = billing_info.phone

                person.reindexObject()
                person.upsertToSalesforce()

            mtool.logoutUser()

        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')

        # Fetch the Person object or the donor
        mbtool = getToolByName(self.context, 'membrane_tool')
        person = mbtool.getUserObject(email)

        donation_name = '%s %s - $%i Monthly Donation' % (account.first_name, account.last_name, sub.quantity)
        # Create the Recurring Donation profile (1 API call)
        data = {
            'type': 'npe03__Recurring_Donation__c',
            'Name': donation_name,
            'npe03__Amount__c': sub.quantity,
            'npe03__Recurring_Donation_Campaign__c': self.context.sf_object_id,
            'npe03__Contact__c': person.sf_object_id,
            'npe03__Installment_Period__c': 'Monthly',
            'npe03__Last_Payment_Date__c': sub.current_period_started_at,
            'npe03__Next_Payment_Date__c': sub.current_period_ends_at,
            'npe03__Open_Ended_Status__c': 'Open',
            'npe03__Paid_Amount__c': sub.quantity,
            'Recurly_ID__c': sub.uuid,
            'npe03__Total_Paid_Installments__c': 1,
        }
        if settings.sf_recurring_donation_record_type:
            data['RecordTypeId'] = settings.sf_recurring_donation_record_type
        recurring_res = sfbc.create(data)

        if not recurring_res[0]['success']:
            raise Exception(recurring_res[0]['errors'][0]['message'])

        recurring_donation = recurring_res[0]
        

        # Create the Opportunity object and Opportunity Contact Role (2 API calls)

        transaction_id = None
        # FIXME - Set the transaction id from the recurly callback data (invoice -> transaction -> reference)

        # FIXME - the name hard codes a monthly billing cycle
        data = {
            'type': 'Opportunity',
            'AccountId': settings.sf_individual_account_id,
            'Success_Transaction_Id__c': transaction_id,
            'npe03__Recurring_Donation__c': recurring_donation['id'],
            'Amount': sub.quantity,
            'Name': donation_name,
            'StageName': 'Posted',
            'CloseDate': datetime.now(),
            'CampaignId': self.context.sf_object_id,
            'Source_Campaign__c': self.context.get_source_campaign(),
            'Source_Url__c': self.context.get_source_url(),
        }
        if settings.sf_opportunity_record_type_recurring:
            data['RecordTypeId'] = settings.sf_opportunity_record_type_recurring
        res = sfbc.create(data)

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        opportunity = res[0]
       
        role_res = sfbc.create({
            'type': 'OpportunityContactRole',
            'OpportunityId': opportunity['id'],
            'ContactId': person.sf_object_id,
            'IsPrimary': True,
            'Role': 'Decision Maker',
        })

        if not role_res[0]['success']:
            raise Exception(role_res[0]['errors'][0]['message'])

        # Create the Campaign Member (1 API Call).  Note, we ignore errors on this step since
        # trying to add someone to a campaign that they're already a member of throws
        # an error.  We want to let people donate more than once.
        # Ignoring the error saves an API call to first check if the member exists
        if settings.sf_create_campaign_member:
            member_res = sfbc.create({
                'type': 'CampaignMember',
                'CampaignId': self.context.sf_object_id,
                'ContactId': person.sf_object_id,
                'Status': 'Responded',
            })
       
        # Record the transaction and its amount in the campaign
        self.context.add_donation(sub.quantity)
 
        return self.request.response.redirect('%s/thank-you?donation_id=%s&amount=%s' % (self.context.absolute_url(), opportunity['id'], sub.quantity))


import random
import time
import json
import hmac
import uuid

from five import grok

from plone.i18n.locales.countries import CountryAvailability

from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.statusmessages.interfaces import IStatusMessage

from dexterity.membrane.membrane_helpers import get_brains_for_email
from plone.dexterity.utils import createContentInContainer

from Acquisition import aq_inner
from zope.component import getMultiAdapter

from zope.site.hooks import getSite

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
            

class DonationFormAuthnetDPM(grok.View):
    """ Renders a donation form setup to submit through Authorize.net's Direct Post Method (DPM) """
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('donation_form_authnet_dpm')
    grok.template('donation_form_authnet_dpm')

    def update(self):
        self.levels = [25,50,100,250,500,1000]
        self.timestamp = ''
        self.sequence = str(uuid.uuid4())
        self.fingerprint_url = self.context.absolute_url() + '/authnet_fingerprint'

        self.relay_url = getSite().absolute_url() + '/post_authnet_dpm_donation'
        self.login_key = get_settings().authnet_login_key

        self.countries = CountryAvailability().getCountryListing()
        self.countries.sort()

    
class AuthnetFingerprint(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.name('authnet_fingerprint')
    grok.require('zope2.View')

    def render(self):
        settings = get_settings()
        # hmac breaks if passed unicode which is ok since Authorize.net keys are ascii
        login_key = str(settings.authnet_login_key)
        transaction_key = str(settings.authnet_transaction_key)
        if not login_key or not transaction_key:
            # FIXME - just raise a 404 instead
            return 'ERROR: Not configured'

        # Sequence # identifying the order. This should be generated on the form's initial load
        # so if the user clicks the button twice Authorize.net can detect the duplicate.
        # Or it can be generated here randomly as long as the AJAX call updates its value in
        # the form.
        fp_sequence = self.request.get('sequence')
        fp_timestamp = str(int(time.time()))
        amount = self.request.get('amount')

        msg = '%s^%s^%s^%s^' % (login_key, fp_sequence, fp_timestamp, amount)
        fp_hash = hmac.new(transaction_key, msg).hexdigest()

        self.request.response.setHeader('Content-Type', 'application/json')
        data = {
            'x_fp_hash': fp_hash,
            #'x_fp_sequence': fp_sequence,
            'x_fp_timestamp': fp_timestamp,
        }
        return json.dumps(data)


class AuthnetCallbackDPM(grok.View):
    grok.context(IPloneSiteRoot)
    grok.name('post_authnet_dpm_donation')
    grok.require('zope2.View')

    def render(self):
        response_code = self.request.form.get('x_response_code', None)
        campaign_id = self.request.form.get('c_campaign_id', None)
       
        pc = getToolByName(self.context, 'portal_catalog') 
        res = pc.searchResults(sf_object_id = campaign_id)
        if not res:
            return 'ERROR: Campaign with ID %s not found' % campaign_id
        campaign = res[0].getObject()

        # If the response was a failure of some kind or another, re-render the form with the error message
        # The response goes back to Authorize.net who then renders it through their servers to the user
        if response_code != '1':
            IStatusMessage(self.request).add(u'There was an error processing your donation.  The error message was (%s).  Please try again or contact us if you continue to have issues' % self.request.get('x_response_reason_text'))
            campaign = aq_inner(campaign)
            view = getMultiAdapter((campaign, self.request), name='view')
            return view()

        # Record the successful transaction
        else:
            settings = get_settings()
            # Look for an existing Plone user
            mt = getToolByName(self.context, 'portal_membership')
            first_name = self.request.form.get('x_first_name', None)
            last_name = self.request.form.get('x_last_name', None)
            email = self.request.form.get('x_email', None)
            phone = self.request.form.get('x_phone', None)
            address = self.request.form.get('x_address', None)
            city = self.request.form.get('x_city', None)
            state = self.request.form.get('x_state', None)
            zipcode = self.request.form.get('x_zip', None)
            country = self.request.form.get('x_country', None)
            amount = int(float(self.request.form.get('x_amount', None)))
            trans_id = self.request.form.get('x_trans_id', None)
    
            res = get_brains_for_email(self.context, email, self.request)
            # If no existing user, create one which creates the contact in SF (1 API call)
            if not res:
                data = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'street_address': address,
                    'city': city,
                    'state': state,
                    'zip': zipcode,
                    'country': country, 
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
                person = res[0].getObject()
    
                person.street_address = address
                person.city = city
                person.state = state
                person.zip = zipcode
                person.country = country
                person.reindexObject()
    
            # Create the Opportunity object and Opportunity Contact Role (2 API calls)
            sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
    
            transaction_id = None
            # FIXME - Set the transaction id from the recurly callback data (invoice -> transaction -> reference)
    
            # FIXME - the name hard codes a monthly billing cycle
            res = sfbc.create({
                'type': 'Opportunity',
                'AccountId': settings.sf_individual_account_id,
                'Success_Transaction_Id__c': trans_id,
                'Amount': amount,
                'Name': '%s %s - $%i One Time Donation' % (first_name, last_name, amount),
                'StageName': 'Posted',
                'CloseDate': datetime.now(),
                'CampaignId': campaign.sf_object_id,
                'Source_Campaign__c': campaign.get_source_campaign(),
                'Source_Url__c': campaign.get_source_url(),
            })
    
            if not res[0]['success']:
                raise Exception(res[0]['errors'][0]['message'])
    
            opportunity = res[0]
        
            mbtool = getToolByName(self.context, 'membrane_tool')
            person = mbtool.getUserObject(email)
    
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
            role_res = sfbc.create({
                'type': 'CampaignMember',
                'CampaignId': campaign.sf_object_id,
                'ContactId': person.sf_object_id,
                'Status': 'Responded',
            })
        
            # Record the transaction and its amount in the campaign
            self.context.add_donation(amount)
    
            return self.request.response.redirect('%s/thank-you?email=%s' % (campaign.absolute_url(), email)) 

        return 'Your transaction failed: %s' % self.request.form


import random
import time
import json
import hmac
import uuid
import urllib

from datetime import datetime

from five import grok

from plone.i18n.locales.countries import CountryAvailability

from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.statusmessages.interfaces import IStatusMessage

from dexterity.membrane.membrane_helpers import get_brains_for_email
from plone.dexterity.utils import createContentInContainer

from AccessControl.SecurityManagement import newSecurityManager

from Acquisition import aq_inner
from zope.component import getMultiAdapter

from zope.site.hooks import getSite

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.utils import get_standard_pricebook_id

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from collective.salesforce.fundraising.us_states import states_list
from collective.salesforce.fundraising.authnet.codes import response_codes
from collective.salesforce.fundraising.authnet.codes import reason_codes


class DonationFormAuthnetDPM(grok.View):
    """ Renders a donation form setup to submit through Authorize.net's Direct Post Method (DPM) """
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('donation_form_authnet_dpm')
    grok.template('donation_form_authnet_dpm')

    form_id = 'donation_form_authnet_dpm'

    def update(self):
        self.settings = get_settings()
        self.update_levels()
        self.update_fingerprint()
        self.update_error()
        self.update_countries()
        self.update_states()

    def update_levels(self):
        level_id = self.request.form.get('levels', self.settings.default_donation_ask_one_time)
        self.levels = None
        for row in self.settings.donation_ask_levels:
            row_id, amounts = row.split('|')
            if row_id == level_id:
                self.levels = amounts.split(',')
        if not self.levels:
            self.levels = self.settings.donation_ask_levels[0].split('|')[1].split(',')

    def update_fingerprint(self):
        self.sequence = str(uuid.uuid4())
        self.fingerprint_url = self.context.absolute_url() + '/authnet_fingerprint'

        self.relay_url = getSite().absolute_url() + '/post_authnet_dpm_donation'
        self.login_key = self.settings.authnet_login_key
        # Handle prefill values passed to form.  This should only happen from authnet errors
        self.amount = self.request.get('x_amount', None)

        self.fingerprint = build_authnet_fingerprint(self.amount, self.sequence)

    def update_error(self):
        self.error = self.request.form.get('error', None)
        response_code = self.request.form.get('response_code',None)
        reason_code = self.request.form.get('reason_code', None)

        self.response_text = None
        self.reason_text = None

        if response_code and reason_code:
            self.response_code = int(response_code)
            self.reason_code = int(reason_code)
            self.response_text = response_codes[self.response_code]
            self.reason_text = reason_codes[self.reason_code]

    def update_countries(self):
        self.countries = CountryAvailability().getCountryListing()
        self.countries.sort()

    def update_states(self):
        self.states = states_list

    def xss_clean(self, value):
        # FIXME: This needs to be implemented
        return value



REDIRECT_HTML = """
    <html>
      <head>
        <script type='text/javascript' charset='utf-8'>
          window.location='%(redirect_url)s';
        </script>
        <noscript>
          <meta http-equiv='refresh' content='1;url=%(redirect_url)s'>
        </noscript>
      </head>
      <body></body>
    </html>
"""

def build_authnet_fingerprint(amount, sequence=None):
    fp_timestamp = str(int(time.time()))

    data = {
            'x_fp_hash': None,
            'x_fp_timestamp': fp_timestamp,
        }

    if not amount:
        return data

    # Generate a sequence if none passed
    if not sequence:
        sequence = str(uuid.uuid4())

    # hmac breaks if passed unicode which is ok since Authorize.net keys are ascii
    settings = get_settings()
    login_key = str(settings.authnet_login_key)
    transaction_key = str(settings.authnet_transaction_key)
    if not login_key or not transaction_key:
        return data

    msg = '%s^%s^%s^%s^' % (login_key, sequence, fp_timestamp, amount)
    data['x_fp_hash'] = hmac.new(transaction_key, msg).hexdigest()

    return data


class AuthnetFingerprint(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.name('authnet_fingerprint')
    grok.require('zope2.View')

    def render(self):
        sequence = self.request.get('sequence', None)
        amount = self.request.get('amount', None)

        data = build_authnet_fingerprint(amount, sequence)

        self.request.response.setHeader('Content-Type', 'application/json')

        return json.dumps(data)


class AuthnetCallbackDPM(grok.View):
    grok.context(IPloneSiteRoot)
    grok.name('post_authnet_dpm_donation')
    grok.require('zope2.View')

    def render(self):
        response_code = int(self.request.form.get('x_response_code'))
        reason_code = int(self.request.form.get('x_response_reason_code'))
        campaign_id = self.request.form.get('c_campaign_id')
        form_name = self.request.form.get('c_form_name')

        pc = getToolByName(self.context, 'portal_catalog')
        res = pc.searchResults(sf_object_id = campaign_id)
        if not res:
            return 'ERROR: Campaign with ID %s not found' % campaign_id
        campaign = res[0].getObject()

        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')

        product = None
        product_id = self.request.form.get('c_product_id', None)
        quantity = self.request.form.get('c_quantity', None)
        pricebook_id = None
        if product_id:
            res = pc.searchResults(sf_object_id=product_id)
            if not res:
                return 'ERROR: Product with ID %s not found' % product_id
            product = res[0].getObject()
            pricebook_id = get_standard_pricebook_id(sfbc)

        # If the response was a failure of some kind or another, re-render the form with the error message
        # The response goes back to Authorize.net who then renders it through their servers to the user
        if response_code != 1:
            IStatusMessage(self.request).add(u'There was an error processing your donation.  The error message was (%s).  Please try again or contact us if you continue to have issues' % self.request.get('x_response_reason_text'))

            redirect_data = {
                'error': form_name,
                'response_code': response_code,
                'reason_code': reason_code,
            }
            first_name = self.request.form.get('x_first_name', None)
            last_name = self.request.form.get('x_last_name', None)
            email = self.request.form.get('x_email', None)
            phone = self.request.form.get('x_phone', None)
            amount = self.request.form.get('x_amount', None)
            if first_name:
                redirect_data['x_first_name'] = first_name
            if last_name:
                redirect_data['x_last_name'] = last_name
            if email:
                redirect_data['x_email'] = email
            if phone:
                redirect_data['x_phone'] = phone
            if amount:
                redirect_data['x_amount'] = int(float(amount))
            redirect_data['send_receipt_email'] = 'true'
            redirect_data = urllib.urlencode(redirect_data)
            redirect_url = campaign.absolute_url() + '?' + redirect_data
            return REDIRECT_HTML % {'redirect_url': redirect_url}

        # Record the successful transaction
        else:
            settings = get_settings()
            # Look for an existing Plone user
            mt = getToolByName(self.context, 'portal_membership')
            first_name = self.request.form.get('x_first_name', None)
            last_name = self.request.form.get('x_last_name', None)

            # lowercase all email addresses to avoid lookup errors if typed with different caps
            email = self.request.form.get('x_email', None)
            if email:
                email = email.lower()

            email_opt_in = self.request.form.get('c_email_signup', None) == 'YES'
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
                    'address': address,
                    'city': city,
                    'state': state,
                    'zip': zipcode,
                    'country': country,
                }

                # Treat the email_opt_in field as a ratchet.  Once toggled on, it stays on even if unchecked
                # on a subsequent donation.  Unsubscribing is the way to prevent emails.
                if email_opt_in:
                    data['email_opt_in'] = email_opt_in

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

                # See if any values are modified and if so, update the Person and upsert the changes to SF
                person = res[0].getObject()
                old_data = [person.address, person.city, person.state, person.zip, person.country, person.phone]
                new_data = [address, city, state, zipcode, country, phone]

                if new_data != old_data:
                    person.address = address
                    person.city = city
                    person.state = state
                    person.zip = zipcode
                    person.country = country
                    person.phone = phone
                    person.reindexObject()

                    person.upsertToSalesforce()

                mtool.logoutUser()

            # Create the Opportunity object and Opportunity Contact Role (2 API calls)

            transaction_id = None
            data = {
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
            }

            if product_id and product is not None:
                # record product donations as a particular type, if possible
                if settings.sf_opportunity_record_type_product:
                    data['RecordTypeID'] = settings.sf_opportunity_record_type_product
                # Set the pricebook on the Opportunity to the standard pricebook
                data['Pricebook2Id'] = pricebook_id

                # Set amount to 0 since the amount is incremented automatically by Salesforce
                # when an OpportunityLineItem is created against the Opportunity
                data['Amount'] = 0

                # Set a custom name with the product info and quantity
                data['Name'] = '%s %s - %s (Qty %s)' % (first_name, last_name, product.title, quantity)
            else:
                # this is a one-time donation, record is as such if possible
                if settings.sf_opportunity_record_type_one_time:
                    data['RecordTypeID'] = settings.sf_opportunity_record_type_one_time

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

            # If there is a product, add the OpportunityLineItem (1 API Call)
            if product_id and product is not None:
                line_item_res = sfbc.create({
                    'type': 'OpportunityLineItem',
                    'OpportunityId': opportunity['id'],
                    'PricebookEntryId': product.pricebook_entry_sf_id,
                    'UnitPrice': product.price,
                    'Quantity': quantity,
                })
                
                if not line_item_res[0]['success']:
                    raise Exception(line_item_res[0]['errors'][0]['message'])

            # Create the Campaign Member (1 API Call).  Note, we ignore errors on this step since
            # trying to add someone to a campaign that they're already a member of throws
            # an error.  We want to let people donate more than once.
            # Ignoring the error saves an API call to first check if the member exists
            if settings.sf_create_campaign_member:
                role_res = sfbc.create({
                    'type': 'CampaignMember',
                    'CampaignId': campaign.sf_object_id,
                    'ContactId': person.sf_object_id,
                    'Status': 'Responded',
                })

            # Record the transaction and its amount in the campaign
            campaign.add_donation(amount)

            # Send the email receipt
            campaign.send_donation_receipt(self.request, opportunity['id'], amount)

            # If this is an honorary or memorial donation, redirect to the form to provide details
            is_honorary = self.request.form.get('c_is_honorary', None)
            if is_honorary == 'true':
                redirect_url = '%s/honorary-memorial-donation?donation_id=%s&amount=%s' % (campaign.absolute_url(), opportunity['id'], amount)
            else:
                redirect_url = '%s/thank-you?donation_id=%s&amount=%s' % (campaign.absolute_url(), opportunity['id'], amount)

            return REDIRECT_HTML % {'redirect_url': redirect_url}

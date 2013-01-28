import random
import time
import json
import hmac
import uuid
import urllib

from datetime import datetime

from five import grok
from zope.component import getUtility

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

from collective.stripe.utils import get_settings as get_stripe_settings
from collective.stripe.utils import IStripeUtility

class StripeDonationForm(grok.View):
    """ Renders a donation form setup to submit through Authorize.net's Direct Post Method (DPM) """
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('donation_form_stripe')
    grok.template('donation_form_stripe')

    form_id = 'donation_form_stripe'

    def update(self):
        self.settings = get_settings()

        if self.request.method == 'POST':
            resp = self.process_donation()

        self.amount = self.request.form.get('amount', None)
        if self.amount is not None:
            self.amount = int(self.amount)

        self.update_levels()
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

    def update_error(self):
        # FIXME: Implement error handling here
        return

    def update_countries(self):
        self.countries = CountryAvailability().getCountryListing()
        self.countries.sort()

    def update_states(self):
        self.states = states_list

    def xss_clean(self, value):
        # FIXME: This needs to be implemented
        return value

    def process_donation(self):
        settings = get_stripe_settings()
        resp = stripe.Charge.create(
            amount=self.request.form.get('amount'),
            card=self.request.form.get('token'),
            currency=settings.currency,
            description='test donation',
        )
        import pdb; pdb.set_trace()
        

    def post_process_donation(self):
        campaign_id = self.request.form.get('campaign_id')
        source_campaign_id = self.request.form.get('source_campaign_id')
        source_url = self.request.form.get('source_url')
        form_name = self.request.form.get('form_name')

        # FIXME: This should really live somewhere else and just be called here
        pc = getToolByName(self.context, 'portal_catalog')
        res = pc.searchResults(
            sf_object_id = campaign_id,
            portal_type = ['collective.salesforce.fundraising.fundraisingcampaign','collective.salesforce.fundraising.personalcampaignpage'],
        )
        if not res:
            # FIXME: Throw a custom exception instead
            return self.request.response.redirect('%s/@@donation_error' % self.context.absolute_url())

        campaign = res[0].getObject()

        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')

        # Handle Donation Product forms
        product = None
        product_id = self.request.form.get('c_product_id', None)
        c_products = self.request.form.get('c_products', None)
        quantity = self.request.form.get('c_quantity', None)
        pricebook_id = None
        if product_id:
            res = pc.searchResults(sf_object_id=product_id, portal_type='collective.salesforce.fundraising.donationproduct')
            if not res:
                return 'ERROR: Product with ID %s not found' % product_id
            product = res[0].getObject()

        if product_id or c_products:
            pricebook_id = get_standard_pricebook_id(sfbc)

        # Handle Product Forms with multiple products, each with their own quantity
        products = []
        if c_products:
            for item in c_products.split(','):
                item_id, item_quantity = item.split(':')
                product_res = pc.searchResults(sf_object_id = item_id, portal_type='collective.salesforce.fundraising.donationproduct')
                if not product_res:
                    return 'ERROR: Product with ID %s not found' % product_id
                products.append({'id': item_id, 'quantity': item_quantity, 'product': product_res[0].getObject()})

            settings = get_settings()

            # Look for an existing Plone user
            mt = getToolByName(self.context, 'portal_membership')
            first_name = self.request.form.get('first_name', None)
            last_name = self.request.form.get('last_name', None)

            # lowercase all email addresses to avoid lookup errors if typed with different caps
            email = self.request.form.get('email', None)
            if email:
                email = email.lower()

            email_opt_in = self.request.form.get('email_signup', None) == 'YES'
            phone = self.request.form.get('phone', None)
            address = self.request.form.get('address', None)
            city = self.request.form.get('city', None)
            state = self.request.form.get('state', None)
            zipcode = self.request.form.get('zip', None)
            country = self.request.form.get('country', None)
            amount = int(float(self.request.form.get('amount', None)))

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
                    'phone': phone,
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
            #    'Success_Transaction_Id__c': trans_id,
                'Amount': amount,
                'Name': '%s %s - $%i One Time Donation' % (first_name, last_name, amount),
                'StageName': 'Posted',
                'CloseDate': datetime.now(),
                'CampaignId': campaign.sf_object_id,
                'Source_Campaign__c': campaign.get_source_campaign(),
                'Source_Url__c': campaign.get_source_url(),
            }

            if product_id and product is not None:
                # FIXME: Add custom record type for Stripe Donations
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

            elif products:
                # record product donations as a particular type, if possible
                if settings.sf_opportunity_record_type_product:
                    data['RecordTypeID'] = settings.sf_opportunity_record_type_product
                # Set the pricebook on the Opportunity to the standard pricebook
                data['Pricebook2Id'] = pricebook_id

                # Set amount to 0 since the amount is incremented automatically by Salesforce
                # when an OpportunityLineItem is created against the Opportunity
                data['Amount'] = 0

                # Set a custom name with the product info and quantity
                parent_form = products[0]['product'].get_parent_product_form()
                title = 'Donation'
                if parent_form:
                    title = parent_form.title
                data['Name'] = '%s %s - %s' % (first_name, last_name, title)
                
            else:
                # this is a one-time donation, record it as such if possible
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

            # If there are Products from a Product Form, create the OpportunityLineItems (1 API Call)
            if products:
                line_items = []
                for item in products:
                    line_item = {
                        'type': 'OpportunityLineItem',
                        'OpportunityId': opportunity['id'],
                        'PricebookEntryId': item['product'].pricebook_entry_sf_id,
                        'UnitPrice': item['product'].price,
                        'Quantity': item['quantity'],
                    }
                    line_items.append(line_item)
                
                line_item_res = sfbc.create(line_items)
                
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

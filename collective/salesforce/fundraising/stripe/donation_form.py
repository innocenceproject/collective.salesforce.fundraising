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
from plone.uuid.interfaces import IUUID
from plone.app.uuid.utils import uuidToObject
from plone.app.async.interfaces import IAsyncService
from zope.app.intid.interfaces import IIntIds
from z3c.relationfield import RelationValue

from zope.event import notify
from zope.lifecycleevent import ObjectModifiedEvent

from AccessControl.SecurityManagement import newSecurityManager

from Acquisition import aq_inner
from zope.component import getMultiAdapter

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.utils import get_standard_pricebook_id

from collective.salesforce.fundraising.donation import build_secret_key
from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from collective.salesforce.fundraising.us_states import states_list

from collective.stripe.utils import get_settings as get_stripe_settings
from collective.stripe.utils import IStripeUtility

import logging
logger = logging.getLogger("Plone")

class DonationFormStripe(grok.View):
    """ Renders a donation form setup to submit through Stripe """
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('donation_form_stripe')
    grok.template('donation_form_stripe')

    form_id = 'donation_form_stripe'

    def update(self):
        self.settings = get_settings()

        self.amount = self.request.form.get('x_amount', None)
        if self.amount is not None:
            self.amount = int(self.amount)

        self.update_levels()
        self.error = None
        self.update_countries()
        self.update_states()

        self.recurring = False
        self.recurring_id = None
        self.recurring_title = None
        campaign = self.context.get_fundraising_campaign()
        if campaign.stripe_recurring_plan:
            self.recurring = True
            self.recurring_id = campaign.stripe_recurring_plan
            # FIXME: Lookup the title from the vocabulary and cache it for a bit
            self.recurring_title = 'Monthly recurring gift'

    def update_levels(self):
        level_id = self.request.form.get('levels', self.settings.default_donation_ask_one_time)
        self.levels = None
        for row in self.settings.donation_ask_levels:
            row_id, amounts = row.split('|')
            if row_id == level_id:
                self.levels = amounts.split(',')
        if not self.levels:
            self.levels = self.settings.donation_ask_levels[0].split('|')[1].split(',')

    def update_countries(self):
        self.countries = CountryAvailability().getCountryListing()
        self.countries.sort()

    def update_states(self):
        self.states = states_list

    def xss_clean(self, value):
        # FIXME: This needs to be implemented
        return value

class ProcessStripeDonation(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.name('process_stripe_donation')

    def render(self):
        """ Attempts to process the donation throught Stripe.  Returns nothing if failure """
        settings = get_stripe_settings()
        stripe_util = getUtility(IStripeUtility)

        self.request.response.setHeader('Content-Type', 'application/json')

        response = {
            'success': False,
            'message': None,
            'redirect': None,
        }

        stripe_api = stripe_util.get_stripe_api()

        try:
            amount = int(self.request.form.get('x_amount'))
        except TypeError:
            logger.info('collective.salesforce.fundraising: Stripe Payment: Validation error due to non-integer amount: %s' % self.request.form.get('x_amount',None))
            response['message'] = 'Please enter a whole dollar amount value for Amount'
            return json.dumps(response)

        # Stripe takes cents
        stripe_amount = amount * 100

        # Is this a recurring donation?
        self.recurring_plan_id = self.request.form.get('recurring_plan', None)
        self.customer_id = None

        # Setup result attributes
        self.stripe_result = None
        self.customer_result = None
        self.subscribe_result = None

        try:
            if not self.recurring_plan_id:
                self.stripe_result = stripe_util.charge_card(
                    token=self.request.form.get('stripeToken'),
                    amount=stripe_amount,
                    description = self.request.form.get('email').lower(),
                    context=self.context,
                )
            else:
                self.customer_id = None
                # FIXME: This will create a new customer each time a recurring donation is submitted
                # need to figure out a secure way to lookup and use existing customer id to allow
                # multiple recurring donations for a person
                #res = self.get_existing_person()
                #if res:
                    #person = res[0].getObject()
                    #customer_id = person.stripe_customer_id
                   
                if not self.customer_id: 
                    self.customer_result = stripe_util.create_customer(
                        token = self.request.form.get('stripeToken'),
                        description = self.request.form.get('email').lower(),
                        context = self.context,
                    )
                    self.customer_id = self.customer_result['id']
                    
                self.subscribe_result = stripe_util.subscribe_customer(
                    customer_id = self.customer_id,
                    plan = self.recurring_plan_id,
                    quantity = amount,
                    context = self.context,
                )
                
            response['success'] = True
            #response['redirect'] = '%s/post_process_stripe_donation?id=%s' % (
            #    self.context.absolute_url(),
            #    resp['id'],
            #)
            
        except stripe_api.CardError, e:
            body = e.json_body
            err  = body['error']
            response['message'] = err['message']
            logger.info('collective.salesforce.fundraising: Stripe Payment CardError: %s' % response['message'])

        except stripe_api.InvalidRequestError, e:
            body = e.json_body
            err  = body['error']
            response['message'] = err['message']
            logger.warning('collective.salesforce.fundraising: Stripe Payment InvalidRequestError: %s' % response['message'])

        except stripe_api.AuthenticationError, e:
            body = e.json_body
            err  = body['error']
            response['message'] = err['message']
            logger.warning('collective.salesforce.fundraising: Stripe Payment AuthenticationError: %s' % response['message'])

        except stripe_api.APIConnectionError, e:
            response['message'] = 'There was a problem connecting with our credit card processor.  Please try again in a few minutes or contact us to report the issue'
            logger.warning('collective.salesforce.fundraising: Stripe Payment APIConnectionError: %s' % response['message'])

        except stripe_api.StripeError, e:
            response['message'] = 'There was an error communicating with our payment processor.  Please try again later or contact us to report the issue'
            logger.warning('collective.salesforce.fundraising: Stripe Payment StripeError: %s' % e.json_body)

        except Exception, e:
            response['message'] = 'There was an error with your payment.  Please try again later or contact us to report the issue'
            logger.warning('collective.salesforce.fundraising: Stripe Payment Other Error: %s' % e) 

        if response['success']:
            try:
                response['redirect'] = self.post_process_donation()
            except Exception, e: 
                response['redirect'] = self.context.get_fundraising_campaign_page().absolute_url() + '/@@post_donation_error'
                logger.warning('collective.salesforce.fundraising: Stripe Post Payment Error: %s' % e)
            
        return json.dumps(response)


    def post_process_donation(self):
        #import pdb; pdb.set_trace()
        page = self.context.get_fundraising_campaign_page()
        source_campaign_id = self.request.form.get('source_campaign_id')
        source_url = self.request.form.get('source_url')
        form_name = self.request.form.get('form_name')

        pc = getToolByName(self.context, 'portal_catalog')

        # Handle Donation Product forms
        product = None
        product_id = self.request.form.get('c_product_id', None)
        c_products = self.request.form.get('c_products', None)
        quantity = self.request.form.get('c_quantity', None)
        pricebook_id = None
        if product_id:
            res = pc.searchResults(sf_object_id=product_id, portal_type='collective.salesforce.fundraising.donationproduct')
            if not res:
                raise ValueError('collective.salesforce.fundraising: Stripe Post Payment Error: Product with ID %s not found' % product_id)
            product = res[0].getObject()

        if product_id or c_products:
            sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
            pricebook_id = get_standard_pricebook_id(sfbc)

        # Handle Product Forms with multiple products, each with their own quantity
        products = []
        if c_products:
            for item in c_products.split(','):
                item_id, item_quantity = item.split(':')
                product_res = pc.searchResults(sf_object_id = item_id, portal_type='collective.salesforce.fundraising.donationproduct')
                if not product_res:
                    raise ValueError('collective.salesforce.fundraising: Stripe Post Payment Error: Product with ID %s not found' % item_id)
                products.append({'id': item_id, 'quantity': item_quantity, 'product': product_res[0].getObject()})

        settings = get_settings()

        # lowercase all email addresses to avoid lookup errors if typed with different caps
        email = self.request.form.get('email', None)
        if email:
            email = email.lower()

        first_name = self.request.form.get('first_name', None)
        last_name = self.request.form.get('last_name', None)
        email_opt_in = self.request.form.get('email_signup', None) == 'YES'
        phone = self.request.form.get('phone', None)
        address = self.request.form.get('address', None)
        city = self.request.form.get('city', None)
        state = self.request.form.get('state', None)
        zipcode = self.request.form.get('zip', None)
        country = self.request.form.get('country', None)
        amount = int(float(self.request.form.get('x_amount', None)))

        # Create the Donation
        intids = getUtility(IIntIds)
        page_intid = intids.getId(page)

        data = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'email_opt_in': email_opt_in,
            'phone': phone,
            'address_street': address,
            'address_city': city,
            'address_state': state,
            'address_zip': zipcode,
            'address_country': zipcode,
            'secret_key': build_secret_key(),
            'campaign': RelationValue(page_intid),
            'amount': amount,
            'stage': 'Posted',
            'products': [],
            'campaign_sf_id': page.sf_object_id,
            'source_campaign_sf_id': page.get_source_campaign(),
            'source_url': page.get_source_url(),
            'payment_method': 'Stripe',
        }
       
        if self.recurring_plan_id:
            data['stripe_plan_id'] = self.recurring_plan_id 
            # FIXME: Get plan title from collective.stripe.plans vocabulary term
            data['title'] = '%s %s - $%i Monthly Recurring Donation' % (first_name, last_name, amount)
        else:
            data['transaction_id'] = self.stripe_result['id']
            data['title'] = '%s %s - $%i One Time Donation' % (first_name, last_name, amount)

        if product_id and product is not None:
            # Set a custom name with the product info and quantity
            data['title'] = '%s %s - %s (Qty %s)' % (first_name, last_name, product.title, quantity)

        elif products:
            # Set a custom name with the product info and quantity
            parent_form = products[0]['product'].get_parent_product_form()
            title = 'Donation'
            if parent_form:
                title = parent_form.title
            data['title'] = '%s %s - %s' % (first_name, last_name, title)
            
        if product_id and product is not None:
            data['products'].append('%s|%s|%s' % product.price, quantity, IUUID(product))

        if products:
            for item in products:
                data['products'].append('%s|%s|%s' % (item['product'].price, item['quantity'], IUUID(item['product'])))

        donation = createContentInContainer(
            page,
            'collective.salesforce.fundraising.donation',
            checkConstraints=False,
            **data
        )

        # No longer needed since this is now triggered via an event listener and pushed into the background to prevent
        # re-running the transaction due to zodb conflicts retrying the transaction again.
        # Record the transaction and its amount in the campaign
        #try:
            #page.add_donation(amount)
        #except Exception, e:
            #logger.warning('collective.salesforce.fundraising: Error adding donation to totals: %s' % e)
            

        # Queue sending of the email receipt - FIXME: rendering receipt currently requires the request which is not possible in async
        #async = getUtility(IAsyncService)
        #async.queueJob(sendDonationReceipt, IUUID(donation))

        # Send receipt immediately
        donation.send_donation_receipt(self.request, donation.secret_key)

        # If this is an honorary or memorial donation, redirect to the form to provide details
        is_honorary = self.request.form.get('is_honorary', None)
        if is_honorary == 'true':
            redirect_url = '%s/honorary-memorial-donation?key=%s' % (donation.absolute_url(), donation.secret_key)
        else:
            redirect_url = '%s?key=%s' % (donation.absolute_url(), donation.secret_key)

        return redirect_url

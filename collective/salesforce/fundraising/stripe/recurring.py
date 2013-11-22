from five import grok
from Acquisition import aq_parent
from zope.component import getUtility
from zope.component.hooks import getSite
from Products.CMFCore.utils import getToolByName
from plone.app.uuid.utils import uuidToObject
from plone.dexterity.utils import createContentInContainer
from collective.stripe.utils import IStripeUtility
from collective.stripe.interfaces import IInvoicePaymentSucceededEvent
from collective.stripe.interfaces import IInvoicePaymentFailedEvent
from collective.stripe.interfaces import ICustomerSubscriptionUpdatedEvent
from collective.stripe.interfaces import ICustomerSubscriptionDeletedEvent
from collective.simplesalesforce.utils import ISalesforceUtility
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.donation import build_secret_key
from collective.salesforce.fundraising.stripe.donation_form import stripe_timestamp_to_date

import logging
logger = logging.getLogger("Plone")

def get_last_donation_for_invoice(invoice):
    # Look for another donation with the same Stripe customer
    pc = getToolByName(getSite(), 'portal_catalog')
    res = pc.searchResults(
        portal_type='collective.salesforce.fundraising.donation',
        stripe_customer_id = invoice['customer'],
        sort_on = 'created',
        sort_order = 'reverse',
    )

    if res:
        return res[0].getObject()


def get_container_for_invoice(invoice):
    """ Get the container where a donation for the invoice should be created """

    mode = 'live'
    if invoice['livemode'] == False:
        mode = 'test'
    stripe_util = getUtility(IStripeUtility)
    stripe_api = stripe_util.get_stripe_api(mode=mode)
    customer = stripe_api.Customer.retrieve(invoice['customer'])

    if customer['description']:
        # container's sf_id is in the third column of a pipe delimited string
        desc_parts = customer['description'].split('|')
        if len(desc_parts) >= 3:
            container_id = desc_parts[2]
            if container_id:
                pc = getToolByName(getSite(), 'portal_catalog')
                res = pc.searchResults(
                    object_provides='collective.salesforce.fundraising.fundraising_campaign.IFundraisingCampaignPage',
                    sf_object_id = container_id,
                    sort_index = 'created',
                    sort_limit = 1,
                )
                if res:
                    return res[0].getObject()

    # Find the site default
    settings = get_settings()
    if settings.default_campaign:
        container = uuidToObject(settings.default_campaign)
        if container:
            return container

    # This is the ultimate fallback.  Find the campaign with the most donations and assume it is the default campaign.
    pc = getToolByName(getSite(), 'portal_catalog')
    res = pc.searchResults(
        portal_type='collective.salesforce.fundraising.fundraisingcampaign',
        sort_on='donations_count',
        sort_order='descending',
    )
    if res:
        return res[0].getObject()


def make_donation_from_invoice(invoice, container):
    last_donation = get_last_donation_for_invoice(invoice)

    mode = 'live'
    is_test = invoice['livemode'] is False

    if invoice['livemode'] == False:
        mode = 'test'

    # For recurring invoices, there should only be one line item
    line_item = invoice['lines']['data'][0]
    plan = line_item['plan']

    # Stripe handles amounts as cents
    amount = (plan['amount'] * line_item['quantity']) / 100


    # In theory, there should never be a case where a previous donation
    # for the same customer and plan does not already exist.  In practice,
    # it happens so try to handle the exception by parsing contact data from
    # card info
    if last_donation is not None:
        # Found last donation, get contact data from it
        data = {
            'title': '%s %s - $%i per %s' % (
                last_donation.first_name,
                last_donation.last_name,
                amount,
                plan['interval'],
            ),
            'first_name': last_donation.first_name,
            'last_name': last_donation.last_name,
            'email': last_donation.email,
            'email_opt_in': last_donation.email_opt_in,
            'phone': last_donation.phone,
            'address_street': last_donation.address_street,
            'address_city': last_donation.address_city,
            'address_state': last_donation.address_state,
            'address_zip': last_donation.address_zip,
            'address_country': last_donation.address_country,
            'source_url': last_donation.source_url,
            'source_campaign_sf_id': last_donation.source_campaign_sf_id,
        }
    else:
        # No last donation found, fetch charge data and attempt to parse
        stripe_util = getUtility(IStripeUtility)
        stripe_api = stripe_util.get_stripe_api(mode=mode)
        charge = stripe_api.Charge.retrieve(invoice['charge'], expand=['card','customer'])
        customer = charge['customer']
        card = charge['card']

        description_parts = customer['description'].split('|')
        first_name = ''
        last_name = ''
        campaign_sf_id = None
        if len(description_parts) >= 1:
            first_name = description_parts[0]
        if len(description_parts) >= 2:
            last_name = description_parts[1]
        if len(description_parts) >= 3:
            campaign_sf_id = description_parts[2]

        address_parts = []
        if card['address_line1']:
            address_parts.append(card['address_line1'])
        if card['address_line2']:
            address_parts.append(card['address_line2'])

        data = {
            'title': '%s %s - $%i per %s' % (
                first_name,
                last_name,
                amount,
                plan['interval'],
            ),
            'first_name': first_name,
            'last_name': last_name,
            'email': customer.email,
            'address_street': '\n'.join(address_parts),
            'address_city': card['address_city'],
            'address_state': card['address_state'],
            'address_zip': card['address_zip'],
            'address_country': card['address_country'],
        }

    # Stripe amounts are in cents
    data['amount'] = amount
    data['stripe_customer_id'] = invoice['customer']
    data['stripe_plan_id'] = plan['id']
    data['transaction_id'] = invoice['charge']
    data['is_test'] = is_test
    data['campaign_sf_id'] = container.sf_object_id
    data['secret_key'] = build_secret_key()
    data['stage'] = 'Posted'
    data['payment_method'] = 'Stripe'
    data['payment_date'] = stripe_timestamp_to_date(invoice['date'])

    # Suppress sending an email receipt
    data['is_receipt_sent'] = True

    # Suppress sending a notification of the donation to a personal fundraiser
    data['is_notification_sent'] = True

    donation = createContentInContainer(
        container,
        'collective.salesforce.fundraising.donation',
        checkConstraints=False,
        **data
    )

    # Send the Stripe monthly email receipt
    donation.send_email_recurring_receipt()

    return donation


def update_donation_from_invoice(donation, invoice):
    mode = 'live'
    is_test = invoice['livemode'] is False

    if invoice['livemode'] == False:
        mode = 'test'

    # For recurring invoices, there should only be one line item
    line_item = invoice['lines']['data'][0]
    plan = line_item['plan']

    # The full charge is needed to determine if a refund was issued
    mode = 'live'
    if invoice['livemode'] == False:
        mode = 'test'
    stripe_util = getUtility(IStripeUtility)
    stripe_api = stripe_util.get_stripe_api(mode=mode)
    charge = stripe_api.Charge.retrieve(invoice['charge'])

    # Stripe handles amounts as cents
    amount = (plan['amount'] * line_item['quantity']) / 100

    # Stripe amounts are in cents
    donation.amount = amount
    donation.stripe_customer_id = invoice['customer']
    donation.stripe_plan_id = plan['id']
    donation.transaction_id = invoice['charge']
    donation.is_test = is_test
    if charge['paid'] and not charge['refunded']:
        donation.stage = 'Posted'
    else:
        donation.stage = 'Withdrawn'

    donation.payment_method = 'Stripe'
    donation.payment_date = stripe_timestamp_to_date(invoice['date'])

    # Ensure no emails get set out from the update
    donation.is_receipt_sent = True
    donation.is_notification_sent = True

    donation.reindexObject()

    return donation


def get_donation_for_invoice(invoice):
    pc = getToolByName(getSite(), 'portal_catalog')

    # Look for a donation with the invoice's successful payment as its transaction_id
    res = pc.searchResults(
        portal_type='collective.salesforce.fundraising.donation',
        transaction_id = invoice['charge'],
        sort_limit = 1,
    )

    if res:
        return res[0].getObject()

def get_email_recurring_receipt_data(invoice):
    line_item = invoice['lines']['data'][0]
    plan = line_item['plan']

    page = get_container_for_invoice(invoice)

    # Query the api to get the customer
    mode = 'live'
    if invoice['livemode'] == False:
        mode = 'test'
    stripe_util = getUtility(IStripeUtility)
    stripe_api = stripe_util.get_stripe_api(mode=mode)
    customer = stripe_api.Customer.retrieve(invoice['customer'])

    thank_you_message = None
    if page.thank_you_message:
        thank_you_message = page.thank_you_message.output

    update_url = '%s/@@update-recurring-donation?id=%s' % (getSite().absolute_url(), invoice['customer'])

    description_parts = customer['description'].split('|')
    first_name = ''
    last_name = ''
    campaign_sf_id = None
    if len(description_parts) >= 1:
        first_name = description_parts[0]
    if len(description_parts) >= 2:
        last_name = description_parts[1]

    # Stripe handles amounts as cents
    amount = (plan['amount'] * line_item['quantity']) / 100

    data = {
        'merge_vars': [
            {'name': 'first_name', 'content': first_name},
            {'name': 'last_name', 'content': last_name},
            {'name': 'amount', 'content': amount},
            {'name': 'update_url', 'content': update_url},
        ],
        'blocks': [
            {'name': 'campaign_thank_you', 'content': thank_you_message},
        ],
    }

    campaign_data = page.get_email_campaign_data()
    data['merge_vars'].extend(campaign_data['merge_vars'])
    data['blocks'].extend(campaign_data['blocks'])

    return data


def get_email_recurring_template(field):
    """ Looks for value of field in settings and tries to look up a template using the value as uuid """
    settings = get_settings()
    uuid = getattr(settings, field, None)
    if not uuid:
        logger.warning('collective.salesforce.fundraising: get_email_recurring_template: No template configured for %s' % field)
        return

    template = uuidToObject(uuid)
    if not template:
        logger.warning('collective.salesforce.fundraising: get_email_recurring_template: No template found for %s' % field)
        return

    return template

def get_customer_email_for_invoice(invoice):
    mode = 'live'
    if invoice['livemode'] == False:
        mode = 'test'
    stripe_util = getUtility(IStripeUtility)
    stripe_api = stripe_util.get_stripe_api(mode=mode)
    customer = stripe_api.Customer.retrieve(invoice['customer'])
    return customer['email']

def send_email_recurring_failed(invoice):
    template = None

    if invoice['attempt_count'] == 1:
        template = get_email_recurring_template('email_recurring_failed_first')
    elif invoice['attempt_count'] == 2:
        template = get_email_recurring_template('email_recurring_failed_second')
    elif invoice['attempt_count'] == 3:
        template = get_email_recurring_template('email_recurring_failed_third')

    if not template:
        return

    mail_to = get_customer_email_for_invoice(invoice)
    if not mail_to:
        logger.warning('collective.salesforce.fundraising: Email Recurring Payment Failed: no email address')
        return

    data = get_email_recurring_receipt_data(invoice)

    return template.send(email = mail_to,
        merge_vars = data['merge_vars'],
        blocks = data['blocks'],
    )

def send_email_recurring_cancelled(invoice):
    template = get_email_recurring_template('email_recurring_cancelled')

    if not template:
        return

    mail_to = get_customer_email_for_invoice(invoice)
    if not mail_to:
        logger.warning('collective.salesforce.fundraising: Email Recurring Cancelled: no email address')
        return

    data = get_email_recurring_receipt_data(invoice)

    return template.send(email = mail_to,
        merge_vars = data['merge_vars'],
        blocks = data['blocks'],
    )


@grok.subscribe(IInvoicePaymentSucceededEvent)
def recurring_payment_succeeded(event):
    invoice = event.data['data']['object']

    # Ignore if there is no charge
    if invoice['charge'] is None:
        return

    donation = get_donation_for_invoice(invoice)

    if donation:
        # If the donation exists, update it with data from the invoice
        res = update_donation_from_invoice(donation, invoice)
        return res

    container = get_container_for_invoice(invoice)
    if not container:
        raise ValueError('cannot find container for donation for the invoice')

    return make_donation_from_invoice(invoice, container)


@grok.subscribe(IInvoicePaymentFailedEvent)
def recurring_payment_failed(event):
    invoice = event.data['data']['object']
    return send_email_recurring_failed(invoice)

@grok.subscribe(ICustomerSubscriptionUpdatedEvent)
def recurring_subscription_updated(event):
    subscription = event.data['data']['object']
    plan = subscription['plan']

    # Fetch the recurring profile from Salesforce
    sfconn = getUtility(ISalesforceUtility).get_connection()
    res = sfconn.query("select Id, npe03__Amount__c, npe03__Next_Payment_Date__c, npe03__Open_Ended_Status__c from npe03__Recurring_Donation__c where Stripe_Customer_ID__c = '%s'" % subscription['customer'])

    # If not found, ignore the change.  The recurring profile will be created by a successful invoice payment
    if res['totalSize'] == 0:
        return "No recurring donation found in Salesforce to be updated"

    data = {}
    recurring = res['records'][0]

    # Check if the amount has changed, if so add to data for change
    # Stripe handles amounts as cents
    amount = (plan['amount'] * subscription['quantity']) / 100
    if recurring['npe03__Amount__c'] != amount:
        data['npe03__Amount__c'] = amount

    # Check if the next billing date has changed, if so add to data for change
    if recurring['npe03__Next_Payment_Date__c'] != subscription['current_period_end']:
        data['npe03__Next_Payment_Date__c'] = subscription['current_period_end']

    # Assume that updated subscriptions are active otherwise the would be deleted
    if recurring['npe03__Open_Ended_Status__c'] != 'Open':
        data['npe03__Open_Ended_Status__c'] = 'Open'

    # If there are no changes, exit
    if not data:
        return "No changes to update in Salesforce"

    # Submit the changes to Salesforce and return the result
    return sfconn.npe03__Recurring_Donation__c.update(recurring['id'], data)
    

@grok.subscribe(ICustomerSubscriptionDeletedEvent)
def recurring_subscription_deleted(event):
    subscription = event.data['data']['object']

    # Fetch the recurring profile from Salesforce
    sfconn = getUtility(ISalesforceUtility).get_connection()
    res = sfconn.query("select Id, npe03__Open_Ended_Status__c from npe03__Recurring_Donation__c where Stripe_Customer_ID__c = '%s'" % subscription['customer'])

    # If not found in Salesforce, do nothing
    if res['totalSize'] == 0:
        return "No recurring donation found in Salesforce to be cancelled"

    # Do nothing if the recurring donation is already marked as Closed in Salesforce
    recurring_id = res['records'][0]['Id']
    if res['records'][0]['npe03__Open_Ended_Status__c'] == 'Closed':
        return "Recurring donation is already closed in Salesforce"

    # Mark the recurring donation as closed in Salesforce
    res = sfconn.npe03__Recurring_Donation__c.update(recurring_id, {'npe03__Open_Ended_Status__c': 'Closed'})

    # FIXME: The email for cancel needs to be implemented but this involves reworking the send_email_recurring_cancelled method to accept a subscription
    #mode = 'live'
    #if plan['livemode'] == False:
        #mode = 'test'
    #stripe_util = getUtility(IStripeUtility)
    #stripe_api = stripe_util.get_stripe_api(mode=mode)
    #invoice = stripe_api.Customer.retrieve(invoice['customer'])
#
    #return send_email_recurring_cancelled(invoice)

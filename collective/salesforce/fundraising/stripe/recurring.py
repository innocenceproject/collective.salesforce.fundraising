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
from collective.stripe.interfaces import ICustomerSubscriptionDeletedEvent
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.donation import build_secret_key

def get_last_donation_for_invoice(invoice):
    # Look for another donation with the same Stripe customer and plan
    pc = getToolByName(getSite(), 'portal_catalog')
    customer_id = invoice['customer']
    plan_id = invoice['lines']['data'][0]['plan']['id']
    res = pc.searchResults(
        portal_type='collective.salesforce.fundraising.donation',
        stripe_customer_id = invoice['customer'],
        stripe_plan_id = invoice['customer'],
        sort_on = 'created',
        sort_order = 'descending',
    )

    if res:
        # Return the parent object of the first donation in the list
        return aq_parent(res[0].getObject())

def get_container_for_donation(invoice):
    last_donation = get_last_donation_for_invoice(invoice)
    container = None

    if last_donation:
        container = aq_parent(last_donation)
    else:
        # Find the site default
        settings = get_settings()
        if settings.default_campaign:
            container = uuidToObject(settings.default_campaign)
        if container:
            return container

    if container is None:
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

    # Suppress sending an email receipt
    data['is_receipt_sent'] = True

    # Send the Stripe monthly email receipt
    # FIXME: Implement me

    donation = createContentInContainer(
        container,
        'collective.salesforce.fundraising.donation',
        checkConstraints=False,
        **data
    )

    return donation


@grok.subscribe(IInvoicePaymentSucceededEvent)
def recurring_payment_succeeded(event):
    invoice = event.data['data']['object']
    
    # Ignore if there is no charge
    if invoice['charge'] is None:
        return

    pc = getToolByName(getSite(), 'portal_catalog')

    # Look for a donation with the invoice's successful payment as its transaction_id
    transaction_id = invoice['charge']
    res = pc.searchResults(
        portal_type='collective.salesforce.fundraising.donation',
        transaction_id = transaction_id,
        sort_limit = 1,
    )
    
    if res:
        # Existing donation found, do nothing
        return

    # Look for a previous donation for the stripe customer id
    res = pc.searchResults(
        portal_type = 'collective.salesforce.fundraising.donation',
        stripe_customer_id = invoice['customer'],
        sort_index = 'created',
        sort_order = 'reverse',
        sort_limit = 1,
    )
    if not res:
        # This handler ignores the first donation in the series and assumes the first
        # donation successfully created a donation object
        return

    container = get_container_for_donation(invoice)
    if not container:
        raise ValueError('cannot find container for donation for the invoice')

    donation = make_donation_from_invoice(invoice, container)
        


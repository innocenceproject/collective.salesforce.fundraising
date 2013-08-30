from Acquisition import aq_base, aq_inner, aq_parent
from five import grok
from zope.component import getUtility
from zope.app.container.interfaces import IObjectAddedEvent
from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from Products.statusmessages.interfaces import IStatusMessage
from plone.directives import dexterity, form
from plone.supermodel import model
from AccessControl import getSecurityManager
from Products.CMFCore.permissions import ModifyPortalContent

from plone.namedfile.interfaces import IImageScaleTraversable
from collective.simplesalesforce.utils import ISalesforceUtility
from collective.salesforce.fundraising.utils import get_standard_pricebook_id
from collective.salesforce.fundraising.stripe.donation_form import DonationFormStripe as BaseDonationFormStripe
from collective.salesforce.fundraising.stripe.donation_form import ProcessStripeDonation as BaseProcessStripeDonation


# Interface class; used to define content-type schema.

class IDonationProduct(model.Schema, IImageScaleTraversable):
    """
    A product such as a shirt or an event ticket which can be "purchased"
    through a donation form
    """

    model.load("models/donation_product.xml")

alsoProvides(IDonationProduct, IContentType)


@grok.subscribe(IDonationProduct, IObjectAddedEvent)
def handleDonationProductCreated(product, event):
    # don't accidentaly acquire the parent's sf_object_id when checking this
    if getattr(aq_base(product), 'sf_object_id', None) is None:
        sfconn = getUtility(ISalesforceUtility).get_connection()

        data = {
            'ProductCode': product.id,
            'Description': product.description,
            'Name': product.title,
            'Donation_Only__c': product.donation_only,
        }
        container = product.get_container()
        if container:
            campaign_id = container.get_parent_sfid()
            product.campaign_sf_id = campaign_id
            data['Campaign__c'] = campaign_id

        res = sfconn.Product2.create(data)
        if not res['success']:
            raise Exception(res['errors'][0])
        product.sf_object_id = res['id']
        product.reindexObject(idxs=['sf_object_id'])
        # set up a pricebook entry for this object
        pricebook_id = get_standard_pricebook_id(sfconn)
        pedata = {'Pricebook2Id': pricebook_id,
                  'Product2Id': product.sf_object_id,
                  'IsActive': True,
                  'UnitPrice': product.price}
        pe_res = sfconn.PricebookEntry.create(pedata)
        if not pe_res['success']:
            req = product.REQUEST
            msg = u'Unable to set price for this product in salesforce'
            IStatusMessage(req).add(msg, type=u'warning')

        # Record the pricebook entry id
        product.pricebook_entry_sf_id = pe_res['id']
    return


class DonationProduct(dexterity.Item):
    grok.implements(IDonationProduct)

    def get_container(self):
        container = aq_parent(aq_inner(self))
        if hasattr(container, 'sf_object_id'):
            return container
        return None

    def get_parent_product_form(self):
        method = getattr(self, 'get_product_form', None)
        if method:
            return method()

#class DonationProductView(grok.View):
#    grok.context(IDonationProduct)
#    grok.require('zope2.View')
#    grok.name('view')
#    grok.template('view')

class ProductFormComponent(grok.View):
    grok.context(IDonationProduct)
    grok.require('zope2.View')
    grok.name('product_form_component')
    grok.template('product_form_component')

    def update(self):
        sm = getSecurityManager()
        self.can_update = sm.checkPermission(ModifyPortalContent, self.context)

    def addcommas(self, number):
        return '{0:,}'.format(number)

class DonationFormStripe(BaseDonationFormStripe):
    grok.context(IDonationProduct)

    def update_levels(self):
        """ Donation levels are not used on a product form """
        return

    def campaign_sf_id(self):
        """get the sf_object_id of the acquisition parent of the donation

        because a donation product may be acquired from a personal fundraising
        page contained within the fundraising page to which the product
        belongs, we must get the campaign id of the correct campaing, the 
        acquisition parent, not the containment parent.
        """
        acquired_parent = aq_parent(self.context)
        return acquired_parent.sf_object_id

class ProcessStripeDonation(BaseProcessStripeDonation):
    grok.context(IDonationProduct)
    grok.name('process_stripe_donation')

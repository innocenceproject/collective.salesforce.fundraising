from Acquisition import aq_base, aq_inner, aq_parent
from five import grok
from zope.app.container.interfaces import IObjectAddedEvent
from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from Products.statusmessages.interfaces import IStatusMessage
from plone.directives import dexterity, form

from plone.namedfile.interfaces import IImageScaleTraversable

from collective.salesforce.fundraising.utils import get_standard_pricebook_id
from collective.salesforce.fundraising.authnet.dpm import DonationFormAuthnetDPM as BaseDonationFormAuthnetDPM
from collective.salesforce.fundraising.authnet.dpm import AuthnetFingerprint as BaseAuthnetFingerprint


# Interface class; used to define content-type schema.

class IDonationProduct(form.Schema, IImageScaleTraversable):
    """
    A product such as a shirt or an event ticket which can be "purchased"
    through a donation form
    """

    form.model("models/donation_product.xml")

alsoProvides(IDonationProduct, IContentType)


@grok.subscribe(IDonationProduct, IObjectAddedEvent)
def handleDonationProductCreated(product, event):
    # don't accidentaly acquire the parent's sf_object_id when checking this
    if getattr(aq_base(product), 'sf_object_id', None) is None:
        sfbc = getToolByName(product, 'portal_salesforcebaseconnector')

        data = {
            'type': 'Product2',
            'ProductCode': product.id,
            'Description': product.description,
            'Name': product.title,
        }
        container = product.get_container()
        if container:
            campaign_id = container.get_parent_sfid()
            product.campaign_sf_id = campaign_id
            data['Campaign__c'] = campaign_id

        res = sfbc.create(data)
        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])
        product.sf_object_id = res[0]['id']
        product.reindexObject(idxs=['sf_object_id'])
        # set up a pricebook entry for this object
        pricebook_id = get_standard_pricebook_id(sfbc)
        pedata = {'type': 'PricebookEntry',
                  'Pricebook2Id': pricebook_id,
                  'Product2Id': product.sf_object_id,
                  'UnitPrice': product.price}
        pe_res = sfbc.create(pedata)
        if not pe_res[0]['success']:
            req = product.REQUEST
            msg = u'Unable to set price for this product in salesforce'
            IStatusMessage(req).add(msg, type=u'warning')
    return


class DonationProduct(dexterity.Item):
    grok.implements(IDonationProduct)

    def get_container(self):
        container = aq_parent(aq_inner(self))
        if hasattr(container, 'sf_object_id'):
            return container
        return None

#class DonationProductView(grok.View):
#    grok.context(IDonationProduct)
#    grok.require('zope2.View')
#    grok.name('view')
#    grok.template('view')

class DonationFormAuthnetDPM(BaseDonationFormAuthnetDPM):
    grok.context(IDonationProduct)
    grok.require('zope2.View')
    grok.name('donation_form_authnet_dpm')
    grok.template('donation_form_authnet_dpm')

    def update(self):
        super(DonationFormAuthnetDPM, self).update()
        self.quantity = self.request.form.get('c_quantity', None)
        if self.quantity == None:
            self.quantity = 0
        self.amount = self.context.price * self.quantity
        self.fingerprint_url = self.context.get_fundraising_campaign().absolute_url() + '/authnet_fingerprint'

    def update_levels(self):
        level_id = self.request.form.get('product_levels', self.settings.default_product_ask)
        self.levels = None
        for row in self.settings.product_ask_levels:
            row_id, amounts = row.split('|')
            if row_id == level_id:
                self.levels = amounts.split(',')
        if not self.levels:
            self.levels = self.settings.product_ask_levels[0].split('|')[1].split(',')


class AuthnetFingerprint(BaseAuthnetFingerprint):
    grok.context(IDonationProduct)

    def update(self):
        super(AuthnetFingerprint, self).update()

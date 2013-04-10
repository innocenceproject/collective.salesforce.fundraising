from Acquisition import aq_base, aq_inner, aq_parent
from five import grok
from zope import schema
from zope.app.container.interfaces import IObjectAddedEvent
from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from Products.statusmessages.interfaces import IStatusMessage
from plone.directives import dexterity, form
from plone.app.textfield import RichText
from Products.CMFCore.permissions import ModifyPortalContent
from AccessControl import getSecurityManager

from plone.namedfile.interfaces import IImageScaleTraversable

from collective.stripe.interfaces import IStripeModeChooser
from collective.salesforce.fundraising.utils import get_standard_pricebook_id
from collective.salesforce.fundraising.authnet.dpm import DonationFormAuthnetDPM as BaseDonationFormAuthnetDPM
from collective.salesforce.fundraising.authnet.dpm import AuthnetFingerprint as BaseAuthnetFingerprint
from collective.salesforce.fundraising.stripe.donation_form import DonationFormStripe as BaseDonationFormStripe
from collective.salesforce.fundraising.stripe.donation_form import ProcessStripeDonation as BaseProcessStripeDonation

class IProductForm(form.Schema):
    """
    A form displaying multiple donation products which total up to a single total.
    """
    title = schema.TextLine(
        title=u"Title",
        description=u"Used for internal reference, not displayed on the form",
    )
    description = schema.TextLine(
        title=u"Description",
        description=u"Used for internal reference, not displayed on the form",
        required=False,
    )

alsoProvides(IProductForm, IContentType)


class IProductFieldset(form.Schema):
    """
    A fieldset grouping donation products
    """

    collapse_on_campaign = schema.Bool(
        title=u"Collapse on Fundraising Campaign?",
        description=u"If checked, this fieldset will be shown initially collapsed on fundraising campaigns",
        required=False,
    )
    collapse_on_personal = schema.Bool(
        title=u"Collapse on Personal Campaign Page?",
        description=u"If checked, this fieldset will be shown initially collapsed on personal campaigns",
        required=False,
    )

alsoProvides(IProductFieldset, IContentType)

class ProductForm(dexterity.Container):
    grok.implements(IProductForm, IStripeModeChooser)
    grok.provides(IStripeModeChooser)

    def get_product_form(self):
        return self

    def get_stripe_mode(self):
        return self.get_fundraising_campaign().get_stripe_mode()

class ProductFieldset(dexterity.Container):
    grok.implements(IProductFieldset)

class ProductFormComponent(grok.View):
    grok.context(IProductFieldset)
    grok.require('zope2.View')
    grok.name('product_form_component')
    grok.template('product_form_component')

    def update(self):
        request_context = self.request.other['PARENTS'][0]
        self.css_class = 'product-fieldset'
        self.collapsed = False
        if request_context.is_personal() and self.context.collapse_on_personal:
            self.collapsed = True
            self.css_class += ' collapsed'
        if not request_context.is_personal() and self.context.collapse_on_campaign:
            self.collapsed = True
            self.css_class += ' collapsed'

    def can_edit(self):
        sm = getSecurityManager()
        return sm.checkPermission(ModifyPortalContent, self.context)

class DonationFormAuthnetDPM(BaseDonationFormAuthnetDPM):
    grok.context(IProductForm)
    grok.require('zope2.View')
    grok.name('donation_form_authnet_dpm')
    grok.template('donation_form_authnet_dpm')

    @property
    def form_id(self):
        return "product_form_%s_donation_form_authnet_dpm" % self.context.id

    def update(self):
        super(DonationFormAuthnetDPM, self).update()
        # FIXME: Change quantity to key/value pairs with sf id
        #self.quantity = self.request.form.get('c_quantity', None)
        #if self.quantity == None:
        #    self.quantity = 0
        # FIXME: new method, calculate amount
        #self.amount = self.context.price * self.quantity
        
        self.fingerprint_url = self.context.get_fundraising_campaign().absolute_url() + '/authnet_fingerprint'

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
        

class AuthnetFingerprint(BaseAuthnetFingerprint):
    grok.context(IProductForm)

    def update(self):
        super(AuthnetFingerprint, self).update()

class DonationFormStripe(BaseDonationFormStripe):
    grok.context(IProductForm)

    def can_edit(self):
        sm = getSecurityManager()
        return sm.checkPermission(ModifyPortalContent, self.context)

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
    grok.context(IProductForm)
    grok.name('process_stripe_donation')

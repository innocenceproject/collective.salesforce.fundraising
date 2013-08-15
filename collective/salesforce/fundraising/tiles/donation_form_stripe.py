from AccessControl import Unauthorized
from zope.component import getMultiAdapter
from collective.cover.tiles.base import IPersistentCoverTile
from collective.cover.tiles.base import PersistentCoverTile
from plone.app.uuid.utils import uuidToObject
from plone.tiles.interfaces import ITileDataManager
from plone.uuid.interfaces import IUUID
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope import schema
from zope.interface import implements


class IDonationFormStripeTile(IPersistentCoverTile):

    uuid = schema.TextLine(title=u'Campaign uuid', readonly=True)


class DonationFormStripeTile(PersistentCoverTile):

    implements(IPersistentCoverTile)

    index = ViewPageTemplateFile("templates/donation_form_stripe.pt")

    is_editable = True
    is_configurable = True

    def donation_form(self):
        donation_form = ''
        uuid = self.data.get('uuid', None)
        try:
            obj = uuid and uuidToObject(uuid)
        except Unauthorized:
            obj = None
        if obj is not None:
            donation_form_view = getMultiAdapter((obj, self.request), name="donation_form_stripe")
            donation_form = donation_form_view()
        return donation_form

    def populate_with_object(self, obj):
        super(DonationFormStripeTile, self).populate_with_object(obj)

        data = {
            'uuid': IUUID(obj, None),  # XXX: can we get None here? see below
        }

        data_mgr = ITileDataManager(self)
        data_mgr.set(data)

    def accepted_ct(self):
        """ Allow types which can render forms
        """
        return ['collective.salesforce.fundraising.fundraisingcampaign', 
                'collective.salesforce.fundraising.personalcampaignpage',
                'collective.salesforce.fundraising.productform',
               ]
            

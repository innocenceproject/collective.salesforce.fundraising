from five import grok
from zope import schema
from zope.interface import alsoProvides
from zope.component import getUtility
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from plone.directives import dexterity
from plone.supermodel import model
from plone import namedfile
from plone.app.textfield import RichText

# Interface class; used to define content-type schema.

class IFundraisingSeal(model.Schema, namedfile.interfaces.IImageScaleTraversable):
    """
    A Fundraising Seal such as awards or fund distribution charts.
    These are shown in the Campaign Seals portlet in condensed form
    with an overlay showing the detailed text when clicked
    """

    blurb = schema.TextLine(
        title=u"Blurb",
        description=u"The short text shown to the right of the Seal in the portlet.  Try to keep this below 50 characters",
    )

    image = namedfile.field.NamedBlobImage(
        title=u"Seal Image",
    )

    more_info_content = RichText(
        title=u"More Info Content",
        description=u"Enter the content that should be displayed in the overlay when someone clicks More Info.  If not provided, More Info and the overlay will not be enabled for this seal",
        required=False,
    )
    

alsoProvides(IFundraisingSeal, IContentType)

class FundraisingSeal(dexterity.Item):
    grok.implements(IFundraisingSeal)

class FundraisingSealView(grok.View):
    grok.context(IFundraisingSeal)
    grok.require('zope2.View')
    grok.name('view')
    grok.template('view')

#class SampleView(grok.View):
#    grok.context(IDonorQuote)
#    grok.require('zope2.View')

    # grok.name('view')

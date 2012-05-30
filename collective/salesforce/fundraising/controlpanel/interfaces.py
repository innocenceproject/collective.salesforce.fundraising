from z3c.form import interfaces

from zope import schema
from zope.interface import Interface
from plone.app.textfield import RichText

from zope.i18nmessageid import MessageFactory

_ = MessageFactory('collective.salesforce.fundraising')


class IFundraisingSettings(Interface):
    """Global settings for collective.salesforce.fundraising
    configuration registry and obtainable via plone.registry.
    """

    default_form_embed = schema.Text(
        title=_(u'Default Form Embed Code'),
        description=_(u'The markup to display a one-time donation form from some external service. '
            u'This is a default which can be overridden for a particular fundraising campaign. '
            u'CAMPAIGN_ID, SOURCE_CAMPAIGN, and SOURCE_URL can be used as placeholders that will '
            u'be filled in automatically.'),
    )

    default_thank_you_message = schema.Text(
        title=_(u"Default Thank You Message"),
        description=_(u"The default Thank You Message for Fundraising Campaigns"),
        default=u"<p>Your donation was processed successfully.  Thank you for your support.</p>",
        required=True,
    )

    default_personal_appeal = schema.Text(
        title=_(u"Default Personal Appeal"),
        description=_(u"The default Personal Appeal for Personal Campaign Pages.  This can be overridden on a campaign by campaign basis"),
        default=u"<p>I am helping raise money for a great organization.  Please donate to help me reach my goal.</p>",
        required=True,
    )

    default_personal_thank_you_message = schema.Text(
        title=_(u"Default Personal Thank You Message"),
        description=_(u"The default Personal Thank You Message for Personal Campaign Pages"),
        default=u"<p>Thank you for your donation and for helping me reach my goal.</p>",
        required=True,
    )

    custom_form_head = schema.Text(
        title=_(u"Custom Form Head"),
        description=_(u"Whatever is entered here is added to the end of the <head> tag on pages where the donation form is displayed.  Use this if you need custom css or javascript for your donation form."),
        default=u"",
        required=False,
    )

    janrain_api_key = schema.Text(
        title=_(u"Janrain API Key"),
        description=_(u"If provided, Janrain integration functionality will be turned on allowing for social login and social sharing"),
        required=False,
    )

    janrain_site_id = schema.Text(
        title=_(u"Janrain Site ID"),
        description=_(u"If you are using Janrain, the Site ID is the name of your instance. You can find it in the urls in the embed code provided through the Janrain control panel"),
        required=False,
    )

    janrain_sharing_app_id = schema.Text(
        title=_(u"Janrain App ID"),
        description=_(u"If you are using Janrain, enter the value for appId in the embed code provided for your sharing widget"),
        required=False,
    )


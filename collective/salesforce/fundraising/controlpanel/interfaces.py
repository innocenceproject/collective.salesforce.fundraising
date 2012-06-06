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

    available_form_views = schema.List(
        title=_(u"Available form views"),
        description=_(u"This is a list of views available on fundraising campaigns which will render the donation form for the campaign.  This list is used as the vocabulary when building new forms"),
        required=True,
        value_type=schema.TextLine(), 
        default=[u'donation_form_authnet_dpm',u'donation_form_recurly'],
    )
    
    default_donation_form_tabs = schema.List(
        title=_(u"Default form view"),
        description=_(u"The name of the form view to be used by default on a fundraising campaign to render the donation form.  This name must match an option in the Available form views field"),
        required=True,
        value_type=schema.TextLine(),
        default=[u'donation_form_authnet_dpm|A one-time donation',u'donation_form_recurly|Monthly donation'],
    )

    sf_individual_account_id = schema.TextLine(
        title=_(u"Salesforce Individual AccountId"),
        description=_(u"The ID of the Account in Salesforce that represents Individuals in the \"bucket account\" model.  This is typically an account named Individual. This account will be used as the default account when creating the Opportuntity object in Salesforce for a donation"),
        required=True,
        default=u'',
    )

    janrain_api_key = schema.TextLine(
        title=_(u"Janrain API Key"),
        description=_(u"If provided, Janrain integration functionality will be turned on allowing for social login and social sharing"),
        required=False,
    )

    janrain_site_id = schema.TextLine(
        title=_(u"Janrain Site ID"),
        description=_(u"If you are using Janrain, the Site ID is the name of your instance. You can find it in the urls in the embed code provided through the Janrain control panel"),
        required=False,
    )

    janrain_sharing_app_id = schema.TextLine(
        title=_(u"Janrain App ID"),
        description=_(u"If you are using Janrain, enter the value for appId in the embed code provided for your sharing widget"),
        required=False,
    )

    janrain_use_extended_profile = schema.Bool(
        title=_(u"Janrain - Use extended profile?"),
        description=_(u"If checked, the auth_info call after authentication will attempt to fetch an extended profile which is only available in the paid versions."),
        required=False,
    )

    authnet_login_key = schema.TextLine(
        title=_(u"Authorize.net Login Key"),
        description=_(u"The login key from your Authorize.net account. If not provided, the Authorize.net DPM donation form will not render"),
        required=False,
    )

    authnet_transaction_key = schema.TextLine(
        title=_(u"Authorize.net Transaction Key"),
        description=_(u"The transaction key from your Authorize.net account. If not provided, the Authorize.net DPM donation form will not render"),
        required=False,
    )

    recurly_subdomain = schema.TextLine(
        title=_(u"Recurly Subdomain"),
        description=_(u"If you want to use Recurly for recurring donation management, enter your subdomain key here."),
        required=False,
    )

    recurly_api_key = schema.TextLine(
        title=_(u"Recurly API Key"),
        description=_(u"If you want to use Recurly for recurring donation management, enter your API key here."),
        required=False,
    )

    recurly_private_key = schema.TextLine(
        title=_(u"Recurly Private Key"),
        description=_(u"If you want to use Recurly for recurring donation management, enter your Private key here."),
        required=False,
    )

    recurly_plan_code = schema.TextLine(
        title=_(u"Recurly Plan Code"),
        description=_(u"If you want to use Recurly for recurring donation management, enter the code for the plan here."),
        required=False,
    )


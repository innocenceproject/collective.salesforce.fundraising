from zope import schema
from zope.interface import Interface
from plone.directives import form
from collective.chimpdrill.schema import ITemplate

class IBaseCampaignEmail(Interface):
    campaign_name = schema.TextLine(
        title=u"Campaign Name",
        description=u"The name of the Fundraising Campaign",
    )
    campaign_url = schema.TextLine(
        title=u"Campaign URL",
        description=u"The URL of the Fundraising Campaign",
    )
    campaign_image_url = schema.TextLine(
        title=u"Campaign Image URL",
        description=u"The URL of the main image for the campaign, if provided",
        required=False,
    )
    campaign_header_image_url = schema.TextLine(
        title=u"Campaign Header Image URL",
        description=u"The URL of the custom header image for the campaign, if provided",
        required=False,
    )

class IBaseHonoraryEmail(Interface):
    donor_first_name = schema.TextLine(
        title=u"Donor First Name",
        description=u"The first name of the donor",
    )
    donor_last_name = schema.TextLine(
        title=u"Donor Last Name",
        description=u"The last name of the donor",
    )
    honorary_first_name = schema.TextLine(
        title=u"Honorary First Name",
        description=u"The first name of the honoree",
    )
    honorary_last_name = schema.TextLine(
        title=u"Honorary Last Name",
        description=u"The last name of the honoree",
    )
    recipient_first_name = schema.TextLine(
        title=u"Recipient First Name",
        description=u"The first name of the recipient",
    )
    recipient_last_name = schema.TextLine(
        title=u"Recipient Last Name",
        description=u"The last name of the recipient",
    )
    amount = schema.Int(
        title=u"Amount",
        description=u"The amount of the donation",
    )
    block_message = schema.TextLine(
        title=u"Message",
        description=u"The message in html format.",
    )

class IHonoraryEmail(form.Schema, ITemplate, IBaseCampaignEmail, IBaseHonoraryEmail):
    """ Schema for the Honorary donation notification email """

class IMemorialEmail(form.Schema, ITemplate, IBaseCampaignEmail, IBaseHonoraryEmail):
    """ Schema for the Memorial donation notification email """

class IThankYouEmail(form.Schema, ITemplate, IBaseCampaignEmail):
    block_receipt = schema.Text(
        title=u"Receipt HTML",
        description=u"The HTML code for the receipt itself",
    )
    block_campaign_thank_you = schema.Text(
        title=u"Campaign Thank You HTML",
        description=u"The campaign's custom thank you message",
    )
    amount = schema.Int(
        title=u"Amount",
        description=u"The amount of the donation",
    )
    first_name = schema.TextLine(
        title=u"First Name",
        description=u"The first name of the donor",
    )
    last_name = schema.TextLine(
        title=u"Last Name",
        description=u"The last name of the donor",
    )


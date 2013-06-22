from zope import schema
from zope.interface import Interface
from plone.supermodel import model
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
        description=u"The URL of the full sized main image for the campaign, if provided",
        required=False,
    )
    campaign_header_image_url = schema.TextLine(
        title=u"Campaign Header Image URL",
        description=u"The URL of the full sized custom header image for the campaign, if provided",
        required=False,
    )
    campaign_goal = schema.Int(
        title=u"Campaign Goal",
        description=u"The goal for the campaign",
    )
    campaign_raised = schema.Int(
        title=u"Campaign Raised",
        description=u"The amount raised thus far by the campaign",
    )
    campaign_percent = schema.Int(
        title=u"Campaign Percent",
        description=u"The percentage of goal completion by the campaign",
    )

    page_name = schema.TextLine(
        title=u"Page Name",
        description=u"If this donation was to a personal campaign page, the name of the page",
    )
    page_fundraiser_first = schema.TextLine(
        title=u"Page Fundraiser First Name",
        description=u"The first name of the fundraiser who created this page",
    )
    page_fundraiser_last = schema.TextLine(
        title=u"Page Fundraiser Last Name",
        description=u"The last name of the fundraiser who created this page",
    )
    page_url = schema.TextLine(
        title=u"Page URL",
        description=u"If this donation was to a personal campaign page, the url of the page",
    )
    page_image_url = schema.TextLine(
        title=u"Page Image URL",
        description=u"If this donation was to a personal campaign page, the url to the full size image for the pagej",
    )
    page_goal = schema.Int(
        title=u"Page Goal",
        description=u"If this donation was to a personal campaign page, the goal for the page",
    )
    page_raised = schema.Int(
        title=u"Page Raised",
        description=u"If this donation was to a personal campaign page, the amount raised thus far by the page",
    )
    page_percent = schema.Int(
        title=u"Page Percent",
        description=u"If this donation was to a personal campaign page, the percentage of goal completion by the page",
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

class IHonoraryEmail(model.Schema, ITemplate, IBaseCampaignEmail, IBaseHonoraryEmail):
    """ Schema for the Honorary donation notification email """

class IMemorialEmail(model.Schema, ITemplate, IBaseCampaignEmail, IBaseHonoraryEmail):
    """ Schema for the Memorial donation notification email """

class IThankYouEmail(model.Schema, ITemplate, IBaseCampaignEmail):
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

class PersonalPageCreated(model.Schema, ITemplate, IBaseCampaignEmail):
    """ Schema for emails thanking fundraiser for creating a personal campaign page """

class PersonalPageDonation(model.Schema, ITemplate, IBaseCampaignEmail):
    amount = schema.Int(
        title=u"Amount",
        description=u"The amount of the donation",
    )
    donor_first_name = schema.TextLine(
        title=u"Donor First Name",
        description=u"The first name of the donor",
    )
    donor_last_name = schema.TextLine(
        title=u"Donor Last Name",
        description=u"The last name of the donor",
    )
    donor_email = schema.TextLine(
        title=u"The Donor's email address",
        description=u"The last name of the donor",
    )

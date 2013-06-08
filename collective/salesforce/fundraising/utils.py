import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from zope.component import getUtility
from Products.CMFCore.utils import getToolByName

from plone.registry.interfaces import IRegistry
from collective.simplesalesforce.utils import ISalesforceUtility
from collective.salesforce.fundraising.controlpanel.interfaces import IFundraisingSettings


def get_settings():
    registry = getUtility(IRegistry)
    return registry.forInterface(IFundraisingSettings, False)

def sanitize_soql(s):
    """ Sanitizes a string that will be interpolated into single quotes
        in a SOQL expression.
    """
    return s.replace("'", "\\'")


def get_standard_pricebook_id(sfconn):
    settings = get_settings()
    has_id_setting = True
    pb_id = ''
    try:
        pb_id = settings.sf_standard_pricebook_id
    except AttributeError:
        False
    if not has_id_setting or not pb_id:
        # the 'standard' pricebook __must__ have an entry before any other
        # pricebooks can, so make sure we get the 'standard' one.
        res = sfconn.query("SELECT Id from Pricebook2 WHERE IsStandard=True")
        pb_id = settings.sf_standard_pricebook_id = unicode(res['records'][0]['Id'])
    return pb_id


def compare_sf_ids(id1, id2):
    """compare two given ids, which may or may not be the same length
    """
    id1, id2 = map(lambda x: x.lower(), [id1, id2])
    if len(id1) == len(id2):
        return id1 == id2

    shrt, lng = sorted([id1, id2], key=lambda x: len(x))
    return shrt == lng[:len(shrt)]


def send_confirmation_email(context, subject, mail_to, email_body):
        # Construct the email bodies
        pt = getToolByName(context, 'portal_transforms')
        txt_body = pt.convertTo('text/-x-web-intelligent', email_body, mimetype='text/html')

        # Determine to and from addresses
        portal_url = getToolByName(context, 'portal_url')
        portal = portal_url.getPortalObject()
        mail_from = '"%s" <%s>' % (portal.getProperty('email_from_name'), portal.getProperty('email_from_address'))

        # Construct the email message                
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = mail_from
        msg['To'] = mail_to
        part1 = MIMEText(txt_body, 'plain')
        part2 = MIMEText(email_body, 'html')

        msg.attach(part1)
        msg.attach(part2)

        # Attempt to send it
        try:
            host = getToolByName(context, 'MailHost')
            # The `immediate` parameter causes an email to be sent immediately
            # (if any error is raised) rather than sent at the transaction
            # boundary or queued for later delivery.
            host.send(msg, immediate=True)

        except smtplib.SMTPRecipientsRefused:
            # fail silently so errors here don't freak out the donor about their transaction which was successful
            pass

def get_person_brains_by_sf_id(context, sf_id):
    pc = getToolByName(self, 'portal_catalog')
    res = pc.searchResults(portal_type='collective.salesforce.fundraising', sf_object_id=sf_id)
    if res:
        return res[0]
    

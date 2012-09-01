from zope.component import getUtility
from plone.registry.interfaces import IRegistry
from collective.salesforce.fundraising.controlpanel.interfaces import IFundraisingSettings


def get_settings():
    registry = getUtility(IRegistry)
    return registry.forInterface(IFundraisingSettings, False)

def sanitize_soql(s):
    """ Sanitizes a string that will be interpolated into single quotes
        in a SOQL expression.
    """
    return s.replace("'", "\\'")


def get_standard_pricebook_id(sfbc):
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
        res = sfbc.query("SELECT Id from Pricebook2 WHERE IsStandard=True")
        pb_id = settings.sf_standard_pricebook_id = unicode(res[0]['Id'])
    return pb_id


def compare_sf_ids(id1, id2):
    """compare two given ids, which may or may not be the same length
    """
    id1, id2 = map(lambda x: x.lower(), [id1, id2])
    if len(id1) == len(id2):
        return id1 == id2

    shrt, lng = sorted([id1, id2], key=lambda x: len(x))
    return shrt == lng[:len(shrt)]

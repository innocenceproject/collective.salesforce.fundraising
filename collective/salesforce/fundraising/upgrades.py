
from Products.CMFCore.utils import getToolByName
import logging

log = logging.getLogger(__name__)


def upgrade_4_to_5(context):
    """Normalize email case for consistent login"""
    pas = getToolByName(context, 'acl_users')
    if pas.getProperty('login_transform') != 'lower':
        log.info("Setting PAS login_transform to 'lower'")
        pas.manage_changeProperties(login_transform='lower')

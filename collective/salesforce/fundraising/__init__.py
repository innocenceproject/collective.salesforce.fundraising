from zope.i18nmessageid import MessageFactory
import logging
logger = logging.getLogger('collective.salesforce.fundraising')

# Set up the i18n message factory for our package
MessageFactory = MessageFactory('collective.salesforce.fundraising')

# Patch member creation
import patch

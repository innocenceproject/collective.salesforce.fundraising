from Products.CMFCore.utils import getToolByName
from collective.salesforce.fundraising import logger


def addCatalogIndexes(context):
    """
    Add indexes to portal_catalog.
    """

    setup = getToolByName(context, 'portal_setup')
    setup.runImportStepFromProfile(
        'profile-collective.salesforce.content:default', 'catalog')

    catalog = getToolByName(context, 'portal_catalog')
    indexes = catalog.indexes()
    
    wanted = (
        ('sf_object_id', 'FieldIndex', None),
        ('donations_total', 'FieldIndex', None),
        ('donations_count', 'FieldIndex', None),
        ('goal', 'FieldIndex', None),
        ('get_percent_goal', 'FieldIndex', None),
    )

    added = []
    for name, meta_type, extra in wanted:
        if name not in indexes:
            catalog.addIndex(name, meta_type)
            added.append(name)
            logger.info("Added %s for field %s.", meta_type, name)
    if added:
        logger.info("Indexing new indexes %s.", ', '.join(added))
        catalog.manage_reindexIndex(ids=added)


def import_various(context):
    """
    Import step for configuration that is not handled in xml files.
    """
    
    # Only run step if a flag file is present
    if context.readDataFile('collective-salesforce-fundraising-various.txt') is not None:
        portal = context.getSite()
        addCatalogIndexes(portal)

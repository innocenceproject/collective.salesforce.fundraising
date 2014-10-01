from setuptools import setup, find_packages
import os

version = '1.11'

setup(name='collective.salesforce.fundraising',
      version=version,
      description="Fundraising for Salesforce.com",
      long_description=open("README.txt").read() + "\n" +
                       open(os.path.join("docs", "HISTORY.txt")).read(),
      # Get more strings from
      # http://pypi.python.org/pypi?%3Aaction=list_classifiers
      classifiers=[
        "Framework :: Plone",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Python Modules",
        ],
      keywords='',
      author='',
      author_email='',
      url='http://svn.plone.org/svn/collective/',
      license='GPL',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['collective', 'collective.salesforce'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'setuptools',
          'rwproperty',
          'simplejson',
          'five.globalrequest',
          #'plone.app.dexterity >= 2',
          #'plone.app.users >= 1.1.4dev',
          'plone.namedfile [blobs]',
          'collective.salesforce.content',
          'collective.pluggablelogin',
          'plone.app.registry',
          'collective.oembed==1.2.5',
          'iso8601',
          'recurly',
          'collective.stripe',
          'collective.chimpdrill',
          'dexterity.membrane',
          'z3c.relationfield',
          'plone.directives.dexterity',
          'plone.app.async',
          'collective.simplesalesforce',
          'collective.cover',
          'collective.googleanalytics',
          # For some reason this is necessary to process
          # a donation even in Plone 4.3
          'plone.app.kss',
          #'zope.app.component',
      ],
      extras_require={
          'test': ['plone.app.testing'],
      },
      entry_points="""
      # -*- Entry points: -*-
      [z3c.autoinclude.plugin]
      target = plone
      """,
      )

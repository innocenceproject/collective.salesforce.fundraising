from setuptools import setup, find_packages
import os

version = '1.0'

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
          'simplejson',
          'five.globalrequest',
          'plone.app.dexterity',
          'plone.app.users >= 1.1.4dev',
          'plone.namedfile [blobs]',
          'collective.salesforce.content',
          'collective.pluggablelogin',
          'plone.app.registry',
          'collective.oembed',
          'iso8601',
          'recurly',
          'collective.stripe',
          'dexterity.membrane',
          'z3c.relationfield',
          'plone.directives.dexterity',
          # -*- Extra requirements: -*-
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

from setuptools import setup, find_packages
import sys, os

version = '6.0.9'

setup(name='WingDBG',
      version=version,
      description="Zope2 to WingIDE debugging driver (unofficial egg porting)",
      long_description="""\
      Zope product that allows Wing to debug Python code running under Zope2
""",
      classifiers=['Framework :: Zope2',
                   'Development Status :: 5 - Production/Stable',
                   'Topic :: Software Development :: Debuggers',
                   'Programming Language :: Zope',
                   ],
      keywords='Zope2 WingIDE debug pdb',
      author='Wingware',
      author_email='support@wingware.com',
      url='http://www.wingware.com/doc/howtos/zope',
      license='MIT',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      # -*- Entry points: -*-

      [z3c.autoinclude.plugin]
      target = plone
      """,
      )

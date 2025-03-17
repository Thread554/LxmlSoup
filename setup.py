from setuptools import setup, find_packages

def readme():
  with open('README.md', 'r') as f:
    return f.read()

setup(
  name='LxmlSoup',
  version='1.6',
  author='Alexander554',
  author_email='gaa.28112008@gmail.com',
  description='f is a set of tools for fast and easy parsing',
  long_description=readme(),
  long_description_content_type='text/markdown',
  packages=find_packages(),
  install_requires=['lxml', 'cssselect'],
  classifiers=[
    'Programming Language :: Python :: 3.11',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent'
  ],
  keywords=['BeautifulSoup', 'bs4', 'lxml', 'Soup', 'LxmlSoup'],
  python_requires='>=3.6'
)

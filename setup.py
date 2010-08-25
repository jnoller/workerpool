try:
    from distribute import setup
except:
    from setuptools import setup

setup(
    name = "WorkerPool",
    version = "0.1",
    scripts = [],
    packages = ['workerpool',],

    # metadata for upload to PyPI
    author = "Jesse Noller",
    author_email = "jnoller@gmail.com",
    description = "Workerpool for threads!",
    #long_description=open('README.txt').read(),
    license = "Apache Software License 2.0",
    keywords = "threads threadpool parallel",
    url = "http://opensource.nasuni.com/bender",
)


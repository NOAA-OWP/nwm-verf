from setuptools import setup, find_packages

VERSION = '0.0.1' 
DESCRIPTION = 'NextGen/NWM forecast verification'
LONG_DESCRIPTION = 'NextGen/NWM forecast verification'

# Setting up
setup(
       # the name must match the folder name
        name="ngen.verf", 
        version=VERSION,
        author="Yuqiong Liu",
        author_email="<yuqiong.liu@ertcorp.com",
        description=DESCRIPTION,
        long_description=LONG_DESCRIPTION,
        packages=find_packages(),
        install_requires=[], # add any additional packages that 
        # needs to be installed along with your package. Eg: 'caer'

        keywords=['python', 'ngen'],
        classifiers= [
            "Development Status :: 3 - Alpha",
            "Intended Audience :: Education",
            "Programming Language :: Python :: 3",
            "Operating System :: MacOS :: MacOS X",
            "Operating System :: Microsoft :: Windows",
        ]
)

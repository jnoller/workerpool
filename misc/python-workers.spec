%define shortname workers
%define shortver 0.1
%define shortrel 4
%define hgver %nil

Name:		python-%{shortname}
Version:	%{shortver}
Release:	%{shortrel}%{?hgver}%{?dist}
Summary:	workers is a work pool for threads
BuildArch: noarch

Group:		Development/Libraries
License:	Apache License, Version 2.0
Source0:	%{shortname}-%{shortver}.tar.gz
BuildRoot:	%(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)

BuildRequires:	python
Requires:	python

%description
Provides a work pool interface to python threads, supporting
a simple interface to make it easy to dispatch functions to
multiple threads.


%prep
%setup -q -n %{shortname}-%{shortver}


%build
python setup.py build


%install
rm -rf $RPM_BUILD_ROOT
python setup.py install -O1 --root=$RPM_BUILD_ROOT \
                        --record=%{shortname}-lst.txt


%clean
rm -rf $RPM_BUILD_ROOT


%files -f %{shortname}-lst.txt
%defattr(-,root,root,-)
%doc


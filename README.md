# LxmlSoup

LxmlSoup is an analogue of BeautifulSoup, containing the most basic and necessary methods. Its speed exceeds bs4 by 5 times. The syntax is the same.

```
0.020386695861816406 - LxmlSoup
0.10153651237487793 - BeautifulSoup
```

## Installation

LxmlSoup requires Python >= 3.7

Install with `pip` from PyPI:

```
pip install LxmlSoup
```

Or cloning the repository:

```
git clone git@github.com:gladkihaa-28/LxmlSoup.git
```

### Examples

```python
from LxmlSoup import LxmlSoup
import requests

html = requests.get('https://sunlight.net/catalog').text
soup = LxmlSoup(html)

links = soup.find_all('a', class_='cl-item-img cl-item-img_loaded')
for link in links:
    print(link.text(), link.get('href'))
```

```python
from LxmlSoup import LxmlSoup
import requests

html = requests.get('https://sunlight.net/catalog').text
soup = LxmlSoup(html)

links = soup.find_all('a', attrs={'itemprop': 'url'})
for link in links:
    print(link.text(), link.get('href'))
```


You can support the author so that updates come out more often.
Sberbank - 2202 2062 9710 1995



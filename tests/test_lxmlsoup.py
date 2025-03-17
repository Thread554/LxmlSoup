import unittest
from LxmlSoup.LxmlSoup import LxmlSoup


with open("sample.html", "r", encoding="utf-8") as file:
    SAMPLE_HTML = file.read()
file.close()


class TestLxmlSoup(unittest.TestCase):

    def setUp(self):
        self.soup = LxmlSoup(SAMPLE_HTML)

    def test_find_all_by_tag(self):
        p_elements = self.soup.find_all('p')
        self.assertEqual(len(p_elements), 2, "Должно быть 2 <p> элемента")

    def test_find_by_class(self):
        a_elements = self.soup.find_all('a', class_='cl-item-img cl-item-img_loaded')
        self.assertEqual(len(a_elements), 1, "Должен быть найден 1 <a> элемент")
        a_element = a_elements[0]
        self.assertEqual(a_element.attribute('href'), 'http://example.com')
        self.assertTrue(a_element.has_attr('data-value'))
        self.assertEqual(a_element.get('data-value'), 'link1')

    def test_find_with_attrs(self):
        element = self.soup.find('div', attrs={'id': 'main'})
        self.assertIsNotNone(element, "Элемент с id='main' должен быть найден")
        self.assertEqual(element.attribute('data-value'), '123')
        element_itemprop = self.soup.find('div', attrs={'itemprop': 'main'})
        self.assertIsNotNone(element_itemprop, "Элемент с itemprop='main' должен быть найден")

    def test_select_css(self):
        header = self.soup.select_one('h1.header')
        self.assertIsNotNone(header, "Элемент h1.header должен быть найден")
        self.assertEqual(header.text().strip(), 'Welcome')
        li_items = self.soup.select('ul.list li.item')
        self.assertEqual(len(li_items), 3, "Должно быть 3 элемента li.item в ul.list")

    def test_text_extraction(self):
        text = self.soup.text()
        self.assertIn('Welcome', text)
        self.assertIn('Footer content', text)

    def test_get_text_and_prettify(self):
        soup_text = self.soup.get_text(separator="|")
        self.assertIn("Welcome", soup_text)
        pretty = self.soup.prettify()
        self.assertIn("\n", pretty, "Метод prettify должен содержать переносы строк")

        h1 = self.soup.find("h1")
        self.assertEqual(h1.get_text(separator="|"), "Welcome")
        self.assertIn("\n", h1.prettify())

    def test_stripped_strings(self):
        h1 = self.soup.find("h1")
        strings = list(h1.stripped_strings)
        self.assertIn("Welcome", strings)

    def test_contents_descendants(self):
        contents = self.soup.contents
        self.assertTrue(any(el.element.tag == "head" for el in contents),
                        "Должен быть найден элемент <head> в contents")
        descendants = self.soup.descendants
        self.assertTrue(any(el.element.tag == "a" for el in descendants),
                        "Должен быть найден элемент <a> в descendants")

    def test_element_navigation(self):
        div_main = self.soup.find('div', attrs={'id': 'main'})
        children = div_main.children()
        self.assertGreaterEqual(len(children), 5, "У div#main должно быть минимум 5 дочерних элементов")
        li_item = self.soup.find('li', attrs={'class': 'item'})
        self.assertIsNotNone(li_item, "Элемент li с классом 'item' должен быть найден")
        parent = li_item.parent()
        self.assertEqual(parent.element.tag, 'ul', "Родитель li должен быть ul")

        first_li = self.soup.find('li', attrs={'class': 'item first'})
        next_li = first_li.next_sibling()
        self.assertIsNotNone(next_li, "Следующий соседний элемент для первого li не должен быть None")
        previous_li = next_li.previous_sibling()
        self.assertEqual(str(previous_li), str(first_li), "Предыдущий сосед должен совпадать с первым li")
        self.assertGreaterEqual(len(first_li.next_siblings()), 1,
                                "У первого li должен быть хотя бы один следующий сосед")
        self.assertGreaterEqual(len(next_li.previous_siblings()), 1,
                                "У next_li должен быть хотя бы один предыдущий сосед")
        self.assertEqual(first_li(), first_li.text(), "__call__ должен возвращать текстовое содержимое")

        li = self.soup.find("li", attrs={"class": "item"})
        ul_parent = li.find_parent("ul")
        self.assertIsNotNone(ul_parent, "Метод find_parent должен вернуть родительский элемент с тегом 'ul'")
        parents = li.find_parents(attrs={"id": "main"})
        self.assertGreaterEqual(len(parents), 1, "Метод find_parents должен вернуть хотя бы одного предка")

    def test_to_html_and_str(self):
        footer = self.soup.find('footer')
        html_out = footer.to_html()
        self.assertIn('<footer', html_out)
        self.assertIn('Footer content', html_out)
        p_element = self.soup.find('p', attrs={'class': 'text'})
        self.assertIsInstance(str(p_element), str)
        self.assertIsInstance(repr(p_element), str)

    def test_get_text_no_strip(self):
        h1 = self.soup.find("h1")
        text = h1.get_text(separator="|", strip=False)
        self.assertIn("Welcome", text)


if __name__ == '__main__':
    unittest.main()

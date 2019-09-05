import threading
import time
import os
import pandas as pd
from queue import Queue
from bs4 import BeautifulSoup
from datetime import datetime
from geopy.geocoders import ArcGIS

from get_kijiji_content import simple_get


def get_content(num):
    part_1 = "https://www.kijiji.ca/b-real-estate/st-johns/house/"
    part_2 = "k0c34l1700113"

    if num == 1:
        url = part_1 + part_2
    else:
        url = part_1 + "page-" + str(num) + "/" + part_2
    webpage_content = simple_get(url)
    if webpage_content:
        soup = BeautifulSoup(webpage_content, "html.parser")
        rent_houses = soup.find_all("div", {"class": "regular-ad"})
        return rent_houses
    else:
        return []


def get_info(html_):
    info_list = []
    attributes = html_.find_all(
        "h3", {"class": "attributeCardTitle-4135421267"}
    )
    for attri in attributes:
        label_1 = attri.next_sibling.find_all(
            "h4", {"class": "realEstateLabel-3766429502"}
        )
        value_1 = [label.next_sibling.string for label in label_1]
        info_list = info_list + [
            label.string+": "+value for label, value in zip(label_1, value_1)
        ]
        label_2 = attri.next_sibling.find_all(
            "h4", {"class": "attributeGroupTitle-2142319834"}
        )
        value_2 = attri.next_sibling.find_all(
            "ul", {"class": "list-1757374920 disablePadding-1318173106"}
        )
        value_ = []
        for ul in value_2:
            values = [item.get("aria-label") for item in ul.find_all("svg")]
            values = [item.split(": ")[1] for item in values if "Yes" in item]
            if values:
                pass
            else:
                values.append("N/A")
            value_.append(", ".join(values))
        info_list = info_list + [
            label.string+": "+value for label, value in zip(label_2, value_)
        ]
    return info_list


def clean_df(df):
    cleaned_df = df.drop_duplicates("url")
    return cleaned_df


class WebScraper(threading.Thread):
    def __init__(self, num):
        super().__init__()
        self.content = get_content(num)
        self.num = num
        self.size = 0
        self.ArcGIS = ArcGIS()

    def run(self):
        for ad in self.content:
            item_url = "https://www.kijiji.ca" + ad.a.get("href")
            # print(item_url)
            item_content = simple_get(item_url)
            if not item_content:
                continue
            item_soup = BeautifulSoup(item_content, "html.parser")
            try:
                item_address = item_soup.find(
                    "span", {"class", "address-3617944557"}
                ).string.replace("\n", "")
            except Exception as e:
                print(f"Address is not found: {item_url}")
                continue

            try:
                latitude = float(item_soup.find(
                    "meta", {"property": "og:latitude"}
                ).get("content"))
                longitude = float(item_soup.find(
                    "meta", {"property": "og:longitude"}
                ).get("content"))
            except Exception as e:
                latitude = None
                longitude = None

            try:
                item_price = item_soup.find(
                    "span", {"class": "currentPrice-2842943473"}
                ).string.replace("\n", "")
            except Exception as e:
                item_price = "Not available"
                print(f"Price is not found: {item_url}")

            try:
                item_title = item_soup.find(
                    "h1", {"class", "title-2323565163"}
                ).text.replace("\n", "")
            except Exception as e:
                item_title = "No title"
                print(f"Title is not found: {item_url}")

            try:
                labels = item_soup.find_all(
                    "dt", {"class": "attributeLabel-240934283"}
                )
                values = item_soup.find_all(
                    "dd", {"class": "attributeValue-2574930263"}
                )
                info_list = [label.string + ": " + value.string for
                             label, value in zip(labels, values)]
                item_info = " *** ".join(info_list)

                if item_info:
                    pass
                else:
                    item_info = " *** ".join(get_info(item_soup))
            except Exception as e:
                item_info = "Not available"
                print(f"Info is not found: {item_url}")

            try:
                des_list = [string for string in item_soup.find(
                    "h3", {"class": "title-1536205785"}
                ).next_sibling.strings]
                des_list = [string.replace("\n", " ") for string in des_list]
                description = "".join(des_list)
            except Exception as e:
                description = "Not available"
                print(f"Description is not found: {item_url}")

            data = [item_title, item_url, item_address, latitude, longitude,
                    item_price, item_info, description]
            data_queue.put(data)
            self.size += 1
            #print(data_queue.qsize())
        print(f"Thread #{self.num} scrapes {self.size} ads")


if __name__ == "__main__":
    data_queue = Queue(maxsize=0)
    kijiji_dict = {
        "title": [],
        "url": [],
        "address": [],
        "latitude": [],
        "longitude": [],
        "price": [],
        "info": [],
        "description": []
    }
    thread_list = []

    begin_time = datetime.now()
    for num in range(1, 51):
        print(f"Working thread {num} is about to start...")
        thread_list.append(WebScraper(num))
        time.sleep(3)

    time.sleep(3)

    for index, every_thread in enumerate(thread_list):
        print(f"Thread #{index+1} is about to scrape...")
        every_thread.start()
        time.sleep(3)

    time.sleep(3)

    for index, every_thread in enumerate(thread_list):
        print(f"Thread #{index+1} is about to join...")
        every_thread.join()

    scrape_time = datetime.now() - begin_time
    print(f"Total scrape time: {scrape_time}")

    begin_time = datetime.now()
    print(f"Totally scrape {data_queue.qsize()} ads")
    while not data_queue.empty():
        data = data_queue.get()
        for index, key in enumerate(kijiji_dict):
            kijiji_dict[key].append(data[index])

    print("Begin to check and geocode address...")
    while None in kijiji_dict["latitude"]:
        for index, value in enumerate(kijiji_dict["address"]):
            if kijiji_dict["latitude"][index] is None:
                try:
                    geo_location = ArcGIS().geocode(value)
                    kijiji_dict["latitude"][index] = geo_location.latitude
                    kijiji_dict["longitude"][index] = geo_location.longitude
                except Exception as e:
                    pass

    df = pd.DataFrame(kijiji_dict)
    df = clean_df(df)
    file_name = datetime.now().strftime("%Y%m%d-%H%M%S") + ".csv"
    df.to_csv(file_name, encoding="utf-8")

    geocode_time = datetime.now() - begin_time
    print(f"Total geocode time: {geocode_time}")
    print(f"Task has been completed. "
          f"Total simulation time: {scrape_time+geocode_time}")

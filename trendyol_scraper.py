from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import json
import time
import os
import re
from datetime import datetime
from urllib.parse import urlparse

def validate_trendyol_url(url):
    if not url or not url.strip():
        return False, "❌ URL boş olamaz!"
    
    url = url.strip()
    
    try:
        parsed = urlparse(url)
        
        if parsed.scheme not in ['http', 'https']:
            return False, "❌ Geçersiz protokol! URL 'http://' veya 'https://' ile başlamalı."
        
        valid_domains = ['trendyol.com', 'www.trendyol.com']
        if parsed.netloc.lower() not in valid_domains:
            return False, f"❌ Sadece Trendyol linkleri kabul edilir! Girdiğiniz domain: {parsed.netloc}"
        
        if not parsed.path or len(parsed.path) < 5:
            return False, "❌ Geçersiz Trendyol linki! Ürün sayfası linki giriniz."
        
        if '-p-' not in parsed.path.lower():
            return False, "❌ Bu bir ürün linki gibi görünmüyor! Lütfen ürün yorum sayfası linkini girin."
        
        dangerous_chars = ['<', '>', '"', "'", ';', 'javascript:', 'data:', 'vbscript:']
        url_lower = url.lower()
        for char in dangerous_chars:
            if char in url_lower:
                return False, f"❌ Güvenlik hatası! URL'de geçersiz karakter tespit edildi: {char}"
        
        return True, "✅ URL geçerli"
        
    except Exception as e:
        return False, f"❌ URL parse hatası: {str(e)}"

def validate_product_page(driver, wait):
    try:
        logo = driver.find_elements(By.CSS_SELECTOR, "a[href='/']")
        if not logo:
            return False, "❌ Bu sayfa Trendyol gibi görünmüyor!"
        
        product_title = driver.find_elements(By.CSS_SELECTOR, "h1, .product-name, span.info-title-text")
        if not product_title:
            return False, "❌ Ürün bilgisi bulunamadı! Lütfen ürün sayfası linkini kullanın."
        
        page_source = driver.page_source.lower()
        if 'review' not in page_source and 'yorum' not in page_source and 'değerlendirme' not in page_source:
            return False, "❌ Bu sayfada yorum bölümü bulunamadı!"
        
        return True, "✅ Sayfa doğrulandı"
        
    except Exception as e:
        return False, f"❌ Sayfa doğrulama hatası: {str(e)}"

def trendyol_yorum_scrape(url, max_reviews=3000):
    print("🔒 URL güvenlik kontrolü yapılıyor...")
    is_valid, message = validate_trendyol_url(url)
    if not is_valid:
        raise ValueError(message)
    print(message)
    
    if '/yorumlar' not in url:
        print("🔄 Ürün linki tespit edildi, yorumlar sayfasına yönlendiriliyor...")
        
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        url = base_url + '/yorumlar'
        
        if parsed.query:
            url += f"?{parsed.query}"
        
        print(f"✅ Yönlendirilen link: {url}")
    else:
        print("✅ Yorumlar sayfası linki tespit edildi")
    
    options = Options()
    
    options.add_argument("--headless=new")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-images")  
    options.add_argument("--blink-settings=imagesEnabled=false")
    
    prefs = {
        "profile.managed_default_content_settings.images": 2,  
        "profile.managed_default_content_settings.stylesheets": 2,  
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    
    options.page_load_strategy = 'eager' 

    remote_url = os.getenv("SELENIUM_REMOTE_URL", "http://chrome:4444/wd/hub")
    driver = webdriver.Remote(command_executor=remote_url, options=options)
    driver.set_page_load_timeout(30)  

    try:
        print(f"🌐 Sayfa yükleniyor: {url[:50]}...")
        driver.get(url)
    except TimeoutException:
        driver.quit()
        raise Exception("⏱️ Sayfa yükleme zaman aşımı! İnternet bağlantınızı kontrol edin.")
    except WebDriverException as e:
        driver.quit()
        raise Exception(f"❌ Sayfa yükleme hatası: {str(e)}")
    
    wait = WebDriverWait(driver, 10)
    
    print("🔍 Sayfa doğrulanıyor...")
    is_valid_page, validation_message = validate_product_page(driver, wait)
    if not is_valid_page:
        driver.quit()
        raise Exception(validation_message)
    print(validation_message)

    data = {
        "product_name": "",
        "reviews": []
    }

    print("📦 Ürün bilgisi çekiliyor...")
    try:
        product_name_element = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.info-title-text"))
        )
        product_name = product_name_element.text.strip()
        
        if not product_name or len(product_name) < 3:
            print("⚠️ Ürün adı bulunamadı, varsayılan isim kullanılıyor.")
            data["product_name"] = "Bilinmeyen Ürün"
        else:
            data["product_name"] = product_name
            print(f"✓ Ürün: {product_name[:60]}{'...' if len(product_name) > 60 else ''}")
    except TimeoutException:
        print("⚠️ Ürün adı bulunamadı (timeout), varsayılan isim kullanılıyor.")
        data["product_name"] = "Bilinmeyen Ürün"
    except Exception as e:
        print(f"⚠️ Ürün adı çekilirken hata: {str(e)}")
        data["product_name"] = "Bilinmeyen Ürün"

    time.sleep(2)  

    try:
        print("🔄 Yorumlar 'Yeniden Eskiye' sıralanıyor...")
        
        sort_opened = False
        try:
            sort_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Önerilen Sıralama') or contains(., 'Sıralama') or contains(@aria-label, 'Sırala')]")
            
            if sort_buttons:
                sort_button = sort_buttons[0]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sort_button)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", sort_button)
                print("   ✓ Sıralama menüsü açıldı")
                sort_opened = True
            else:
                raise Exception("Sıralama butonu bulunamadı")
                
        except Exception as e:
            try:
                sort_button = driver.find_element(By.CSS_SELECTOR, "button.sort-dropdown-button, button[class*='sort']")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sort_button)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", sort_button)
                print("   ✓ Sıralama menüsü açıldı (alternatif)")
                sort_opened = True
            except:
                print("   ⚠️ Sıralama butonu bulunamadı")
        
        if not sort_opened:
            raise Exception("Sıralama menüsü açılamadı")
        
        time.sleep(1.5) 
        
        newest_clicked = False
        
        try:
            possible_texts = [
                "Yeniden Eskiye",
                "En Yeni",
                "En Yeniler", 
                "Newest First",
                "Yeni Yorumlar"
            ]
            
            for text in possible_texts:
                try:
                    newest_option = driver.find_element(By.XPATH, f"//button[contains(text(), '{text}') or contains(., '{text}')]")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", newest_option)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", newest_option)
                    newest_clicked = True
                    print(f"   ✓ '{text}' seçeneği seçildi")
                    break
                except:
                    continue
        except:
            pass
        
        if not newest_clicked:
            try:
                dropdown_options = driver.find_elements(By.XPATH, "//div[contains(@class, 'dropdown')]//button | //ul[contains(@class, 'dropdown')]//li//button")
                
                print(f"   → {len(dropdown_options)} adet sıralama seçeneği bulundu")
                
                for idx, option in enumerate(dropdown_options):
                    try:
                        option_text = option.text.strip().lower()
                        print(f"   → Seçenek {idx+1}: {option_text}")
                        
                        if any(keyword in option_text for keyword in ['yeni', 'newest', 'recent']):
                            driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", option)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", option)
                            newest_clicked = True
                            print(f"   ✓ Seçenek tıklandı: {option_text}")
                            break
                    except:
                        continue
                        
            except Exception as e:
                print(f"   ⚠️ Seçenekler listelenemedi: {str(e)[:50]}")
        
        if not newest_clicked:
            try:
                all_buttons = driver.find_elements(By.XPATH, "//div[contains(@class, 'dropdown')]//button[not(contains(@aria-label, 'Önerilen'))]")
                if len(all_buttons) >= 1:
                    driver.execute_script("arguments[0].click();", all_buttons[0])
                    newest_clicked = True
                    print(f"   ✓ İlk alternatif seçenek seçildi")
            except:
                pass
        
        if not newest_clicked:
            print("   ⚠️ 'Yeniden Eskiye' seçeneği bulunamadı")
            raise Exception("Seçenek bulunamadı")
        
        time.sleep(2.5) 
        print("✓ Yorumlar yeniden eskiye sıralandı!")
        
    except Exception as e:
        print(f"⚠️ Sıralama yapılamadı, varsayılan sıralama ile devam ediliyor.")
        print(f"   Not: Varsayılan sıralama genelde 'Önerilen' olur, ancak yine de yorumlar çekilecek.")
        time.sleep(1)

    print(f"⚡ Yorumlar yükleniyor... (Maksimum: {max_reviews} yorum)")

    scroll_script = """
        let scrollCount = 0;
        const maxScrolls = 200;
        const scrollInterval = setInterval(() => {
            window.scrollTo(0, document.body.scrollHeight);
            scrollCount++;
            const reviewCount = document.querySelectorAll('div.review').length;
            if (scrollCount >= maxScrolls || reviewCount >= arguments[0]) {
                clearInterval(scrollInterval);
            }
        }, 500);
    """

    driver.execute_script(scroll_script, max_reviews)

    last_count = 0
    stable_count = 0
    max_wait_time = 180
    start_time = time.time()

    while time.time() - start_time < max_wait_time:
        time.sleep(2)
        current_count = len(driver.find_elements(By.CSS_SELECTOR, "div.review"))
        if current_count != last_count and current_count > 0:
            print(f"   Yüklenen: {current_count} yorum")
        if current_count >= max_reviews:
            print(f"✓ Maksimum {max_reviews} yoruma ulaşıldı!")
            break
        if current_count == last_count:
            stable_count += 1
            if stable_count >= 3:
                print("✓ Tüm yorumlar yüklendi.")
                break
        else:
            stable_count = 0
        last_count = current_count

    print(f"\n📊 {last_count} yorum işleniyor...")

    if last_count == 0:
        print("⚠️ Hiç yorum bulunamadı!")
        driver.quit()
        return data

    print("📖 Uzun yorumlar genişletiliyor...")

    expand_script = """
        const reviews = document.querySelectorAll('div.review');
        let clickedCount = 0;
        reviews.forEach((review) => {
            try {
                const allButtons = review.querySelectorAll('button, a, span');
                for (let elem of allButtons) {
                    const text = elem.textContent || '';
                    if (text.includes('Devamını Oku') ||
                        text.includes('Devamını') ||
                        text.includes('Read More') ||
                        text.includes('show more')) {
                        if (elem.tagName === 'BUTTON' || elem.tagName === 'A') {
                            elem.click();
                            clickedCount++;
                            break;
                        } else if (elem.onclick || elem.parentElement.onclick) {
                            elem.click();
                            clickedCount++;
                            break;
                        }
                    }
                }
            } catch(e) {}
        });
        return clickedCount;
    """

    try:
        clicked_count = driver.execute_script(expand_script)
        if clicked_count > 0:
            print(f"   ✓ {clicked_count} yorum genişletildi")
            time.sleep(2)
        else:
            print("   ℹ 'Devamını Oku' butonu bulunamadı")
    except Exception as e:
        print(f"   ⚠️ Buton tıklama hatası (devam ediliyor): {str(e)[:50]}")

    extract_script = """
        const reviews = document.querySelectorAll('div.review');
        const data = [];
        reviews.forEach((review) => {
            let comment = null;
            let date = null;
            try {
                const commentEl = review.querySelector('span.review-comment');
                comment = commentEl ? commentEl.textContent.trim() : null;
            } catch(e) {}
            try {
                const dateEl = review.querySelector('.detail-item.date');
                date = dateEl ? dateEl.textContent.trim() : null;
            } catch(e) {}
            if (comment && comment.length > 0) {
                data.push({ comment: comment, date: date });
            }
        });
        return data;
    """

    try:
        reviews_data = driver.execute_script(extract_script)
        if not reviews_data or len(reviews_data) == 0:
            print("⚠️ Yorumlar çekilemedi!")
            driver.quit()
            return data
        valid_reviews = [r for r in reviews_data if r.get('comment') and len(r.get('comment', '').strip()) > 0]
        data["reviews"] = valid_reviews[:max_reviews]
        print(f"✅ Toplam {len(data['reviews'])} geçerli yorum çekildi!")
    except Exception as e:
        print(f"❌ Yorumlar çekilirken hata: {str(e)}")
        driver.quit()
        raise Exception(f"Veri çekme hatası: {str(e)}")

    driver.quit()
    return data
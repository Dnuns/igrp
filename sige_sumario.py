'''
Esta é a minha segunda automação em python. O que o programa faz:

Iª PARTE:
    *+ entrar no site da nosi;
    *+ colocar o utilizador e a password;
    *+ entrar no SIGE (Sistema Integrado de Gestao Escolar);
    *+ir para o campo de escrever o sumário

'''

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep


# Iª PARTE

browser = webdriver.Firefox()
browser.get('https://nosiapps.gov.cv/redglobal/redglobal.glb_dispatcher.login')

browser.implicitly_wait(20)

for i in range (0,2): # fazer login

    esperar_login = WebDriverWait(browser, 20)
    utilizador = esperar_login.until(EC.element_to_be_clickable((By.NAME, 'p_login')))
    browser.find_element_by_name('p_login').send_keys('David.Nunes')
    Keys.TAB
    password = esperar_login.until(EC.element_to_be_clickable((By.NAME, 'p_password')))
    browser.find_element_by_name('p_password').send_keys('Davesrs2021')
    browser.find_element_by_name('p_button').click()
    browser.implicitly_wait(20)

browser.implicitly_wait(20)
browser.find_element_by_class_name('app-icon').click()

esperar_menu = WebDriverWait(browser,20)
menu_lateral = esperar_menu.until(EC.element_to_be_clickable((By.ID,'side-bar-ctrl')))
browser.find_element_by_id('side-bar-ctrl').click()#abrir o menu

menu_gestao_disciplina = esperar_menu.until(EC.element_to_be_clickable((By.XPATH,'/html/body/form/div[1]/div/div[1]/ul/li[2]/a')))
browser.find_element_by_xpath('/html/body/form/div[1]/div/div[1]/ul/li[2]/a').click()#Menu gestao de disciplina

browser.find_element_by_xpath('/html/body/form/div[1]/div/div[1]/ul/li[2]/ul/li[2]/a/span').click()# Menu principal do professor

sala_de_aula = esperar_menu.until(EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[2]/a/span')))
browser.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[2]/a/span').click()# menu sala de aula

browser.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/div/div[2]/div/div/div/div/div/a[2]/span').click() #submenu resumo do dia









#sleep(10)
#browser.close()

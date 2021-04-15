'''
Esta é a minha segunda automação em python. O que o programa faz:

Iª PARTE:
    *+ entrar no site da nosi;
    *+ colocar o utilizador e a password;
    *+ entrar no SIGE (Sistema Integrado de Gestao Escolar);

IIª PARTE:
    * fazer download da lista dos alunos por turma;
    * mostrar output numa folha de calculos (se possível organizado e formatado)

IIIª PARTE:
    *fazer upload com inputs de dados introduzidos na folha de cálculo baixado
'''
import config
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup as bs
from time import sleep


# Iª PARTE

browser = webdriver.Firefox()
browser.get('https://nosiapps.gov.cv/redglobal/redglobal.glb_dispatcher.login')

browser.implicitly_wait(20)

for i in range (0,2): # fazer login

    esperar_login = WebDriverWait(browser, 10)
    utilizador = esperar_login.until(EC.element_to_be_clickable((By.NAME, 'p_login')))
    browser.find_element_by_name('p_login').send_keys(config.username)
    Keys.TAB
    password = esperar_login.until(EC.element_to_be_clickable((By.NAME, 'p_password')))
    browser.find_element_by_name('p_password').send_keys(config.password)
    browser.find_element_by_name('p_button').click()

browser.find_element_by_class_name('title-desc').click()

esperar = WebDriverWait(browser,10)

menu_lateral = esperar.until(EC.element_to_be_clickable((By.ID,'side-bar-ctrl')))
browser.find_element_by_id('side-bar-ctrl').click()#abrir o menu

menu_gestao_disciplina = esperar.until(EC.element_to_be_clickable((By.XPATH,'/html/body/form/div[1]/div/div[1]/ul/li[2]/a')))
browser.find_element_by_xpath('/html/body/form/div[1]/div/div[1]/ul/li[2]/a').click()#Menu gestao de disciplina vertical
browser.find_element_by_xpath('/html/body/form/div[1]/div/div[1]/ul/li[2]/ul/li[2]/a/span').click()# Menu principal do professor

gestao_disciplina = esperar.until(EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[3]/a/span')))
browser.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[3]/a/span').click()# menu gestao_disciplina horizontal

browser.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/div/div[3]/div/div/div/div/div/a[3]/span').click()# atribuir notas




# IIª PARTE

filtro_nota = esperar.until(EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/div/div[2]/div/div[4]/div[2]/div/div/div[2]/div/div[3]/span/span[1]/span')))
browser.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[4]/div[2]/div/div/div[2]/div/div[3]/span/span[1]/span').click()# atribuir notas filtro ano





sleep(10)
browser.close()

'''
O que o script faz:

    + entrar no site da nosi;
    + colocar o utilizador e a password;
    + entrar no SIGE (Sistema Integrado de Gestao Escolar);
    + ir para o campo de escrever o sumário

'''
import config
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep


browser = webdriver.Firefox()

def login():

    browser.implicitly_wait(20)
    browser.get('https://nosiapps.gov.cv/redglobal/redglobal.glb_dispatcher.login')
    # fazer login
    for i in range (0,2):

        wait_login = WebDriverWait(browser, 20)
        utilizador = wait_login.until(EC.element_to_be_clickable((By.NAME, 'p_login')))
        browser.find_element_by_name('p_login').send_keys(config.username)

        Keys.TAB

        password = wait_login.until(EC.element_to_be_clickable((By.NAME, 'p_password')))
        browser.find_element_by_name('p_password').send_keys(config.password)

        button = wait_login.until(EC.element_to_be_clickable((By.NAME, 'p_button')))
        browser.find_element_by_name('p_button').click()
        sleep(3)


def summary_page():

    #icone
    browser.implicitly_wait(20)
    browser.find_element_by_class_name('app-icon').click()

    #abrir o menu
    wait_menu = WebDriverWait(browser,20)
    menu_lateral = wait_menu.until(EC.element_to_be_clickable((By.ID,'side-bar-ctrl')))
    browser.find_element_by_id('side-bar-ctrl').click()

    #Menu gestao de disciplina
    menu_gestao_disciplina = wait_menu.until(EC.element_to_be_clickable((By.XPATH,'/html/body/form/div[1]/div/div[1]/ul/li[2]/a')))
    browser.find_element_by_xpath('/html/body/form/div[1]/div/div[1]/ul/li[2]/a').click()

    # Menu principal do professor
    menu_p_professor = wait_menu.until(EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[2]/a/span')))
    browser.find_element_by_xpath('/html/body/form/div[1]/div/div[1]/ul/li[2]/ul/li[2]/a/span').click()

    # menu sala de aula
    sala_aula = wait_menu.until(EC.element_to_be_clickable((By.XPATH,'/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[2]/a/span')))
    browser.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[2]/a/span').click()

    #submenu resumo do dia
    resumo_dia = wait_menu.until(EC.element_to_be_clickable((By.XPATH,'/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/div/div[2]/div/div/div/div/div/a[2]/span')))
    browser.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/div/div[2]/div/div/div/div/div/a[2]/span').click()


#Init the script
login()
summary_page()

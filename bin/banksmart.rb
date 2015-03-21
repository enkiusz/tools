#!/usr/bin/env ruby

require 'json'

bank_bic = 'PBPBPLPWFMB'
bank_cc = 'PL'

class UIDLComponent
  attr_accessor :id, :type, :props, :content, :children

  def initialize(type)
    @type = type
    @props = {}
    @children = []
  end

end

def UIDL_build(obj, types)
  type = obj.shift.to_i
  if types.has_key?(type)
    type = types[type]
  end
  c = UIDLComponent.new(type)
  
  c.props = obj.shift
  
  obj.each do |child|
    if child.respond_to?('each')
      c.children << UIDL_build(child, types)
    else
      c.content = child
    end
  end

  return c
end

class UIDL_JSONMsg
  attr_accessor :types, :changes, :meta, :resources, :locales

  def initialize(msg_json)
    json = JSON.parse(msg_json)[0]
    
    @types = json['typeMappings'].invert
    @changes = UIDL_build(json['changes'][0], @types)
    @meta = json['meta']
    @resources = json['resources']
    @locales = json['locales']
  end
  
end

#
# FIXME: This "HTML generator" is very primitive, make something better.
#
def UIDL_html(c)
  type = c.type
  props = c.props
  content = c.content

  s = ""
  s << "<div type='#{type}' "
  props.each { |name,value|
    s << "#{name}='#{value}' "
  }
  s << ">"
  
  c.children.each do |child|
    s << UIDL_html(child)
  end
  if content.respond_to?('length') and content.length > 0
    s << "#{content}"
  end
  s << "</div>"
  return s
end

# Default options
options = {
  identity: nil,
  secret: nil,
  login_url: 'https://online.banksmart.pl/bim-webapp/smart/login',
  verbose: false
}

require 'optparse'
argv0="banksmart.rb"

optparse = OptionParser.new do|opts|
   # Set a banner, displayed at the top
   # of the help screen.
   opts.banner = "Usage: #{argv0} [options]"
 
   # Define the options, and what they do
   opts.on( '-v', '--verbose', 'Output more information' ) do
     options[:verbose] = true
   end
 
   opts.on( '--identity ID', 'Set the user identity (login name).' ) do |arg|
     options[:identity] = arg
   end
   
   opts.on( '--login_url URL', "Set initial login URL (default is '#{options[:login_url]}'" ) do |arg|
     options[:login_url] = arg
   end
   
   # This displays the help screen, all programs are
   # assumed to have this option.
   opts.on( '-h', '--help', 'Display this screen' ) do
     puts opts
     exit
   end
 end
 
 optparse.parse!

if options[:identity] == nil
  puts "Identity must be set."
  Process.exit(1)
end

if options[:secret] == nil or options[:secret].length == 0
  require 'highline/import'
  options[:secret] = ask("Enter password for identity '#{options[:identity]}' accessing URL '#{options[:login_url]}") { |q| q.echo = false }
end

# From original JS:
# function sendLoginRequestToBI() {
#     var a = document.getElementById("password").value,
#         b = new RSAKey;
#     b.setPublic(window._key_n, window._key_e);
#     a = {
#         password: b.encrypt(a)
#     };
#     storeElemValue("nik", a);
#     storeElemValue("paybylink_qs", a);
#     storeElemValue("paybylink_mac", a);
#     new Ajax("login", endLogin, _encode(a))
# }
#             //<![CDATA[
#             _key("b703da6dfaf6a07f34bd936158c5dc8c42e0601caa5b4beeba1412a0d3f898c1655d14f90dda1deea2ec2aac89fee7fd867634327e03f3f737b779118ad01115c5344e981c5bc169fa11bbaad8efcd5f28639066719e6d403a7fae13e8ba88ee0a88edbd28b8802b5e514bdcef837a379f3268ee190b80a3fd7cd484314fa045",
#                  "10001");
#             //]]>

#
# This key looks to be static but it would be better to fetch it every time from the login form page.
#
public_key = "b703da6dfaf6a07f34bd936158c5dc8c42e0601caa5b4beeba1412a0d3f898c1655d14f90dda1deea2ec2aac89fee7fd867634327e03f3f737b779118ad01115c5344e981c5bc169fa11bbaad8efcd5f28639066719e6d403a7fae13e8ba88ee0a88edbd28b8802b5e514bdcef837a379f3268ee190b80a3fd7cd484314fa045"
exponent = "10001"

require 'openssl'

pub = OpenSSL::PKey::RSA::new(public_key.length*4)
pub.n = OpenSSL::BN::new public_key, 16
pub.e = OpenSSL::BN::new exponent, 16

ciphertext = pub.public_encrypt(options[:secret]).unpack('H*')[0]

require 'mechanize'

mechanize = Mechanize.new

if options[:verbose]
  require 'logger'
  mechanize.log = Logger.new(STDERR)
end

mechanize.user_agent_alias = 'Mac Safari'

# Initial get to have cookies
mechanize.get(options[:login_url])

page = mechanize.post(options[:login_url], { 'nik' => options[:identity], 'password' => ciphertext }, { 'X-Requested-With' => 'XMLHttpRequest' })
login_result = JSON.parse(page.body)
if login_result["status"] != "OK"
  puts "Login failure, returned JSON '#{page.body}'"
  Process.exit(1)
end

main_uri = '/bim-webapp/bi/UIDL?repaintAll=1'

accounts_page = mechanize.get(main_uri)

msg = UIDL_JSONMsg.new(accounts_page.body.gsub(/^for\(;;\);/,''))
html_s =  UIDL_html(msg.changes)

require 'nokogiri'
page = Nokogiri::HTML(html_s, &:noblanks)

accounts = {}
page.css("div#PID_Saccounts_list").css('div[style-3="cbp-amount-positive"]').each { |account|
  account_name = account.css('div[style="cbp-account-name"]').text
  account_iban = account.css('div[style="cbp-account-number"]').text.delete(' ')
  
  # Skip rows which are not proper accounts
  if account_iban.length == 0
    next
  end
  
  account_iban = 'PL' + account_iban

  status = account.css('div[style="cbp-status"]').text
  
  # Account credit limit must be accessed using explicit column counting
  credit_limit = account.css('div[type="com.vaadin.ui.HorizontalLayout"]')[2].text

  # Ditto for account balance and available funds
  b = account.css('div[type="com.vaadin.ui.HorizontalLayout"]')[3]
  balance = [ b.css('div[style="cbp-balance"]').text.gsub(/,/,'.').gsub(/[[:space:]]/,''), b.css('div[style="cbp-currency"]').text ].join(' ')

  a = account.css('div[type="com.vaadin.ui.HorizontalLayout"]')[4]
  available = [ a.css('div[style="cbp-balance"]').text.gsub(/,/,'.').gsub(/[[:space:]]/,''), a.css('div[style="cbp-currency"]').text ].join(' ')

  accounts[account_iban] = { iban: account_iban, name: account_name, status: status, balance: balance, available: available }
}

puts accounts

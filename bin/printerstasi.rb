#!/usr/bin/env ruby
# -*- coding: utf-8 -*-
# The MIT License (MIT)

# Copyright (c) 2015 Maciej Grela <enki@fsck.pl>

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Database schema:
# CREATE TABLE print_jobs ( _uid varchar PRIMARY KEY NOT NULL, _ctime varchar, Unk1 varchar, UserId varchar, Filename varchar, Unk2 varchar, Pages varchar, JobId varchar, Timestamp varchar, AuthenticationInfo varchar, StateText varchar, State integer, Unk3 integer, Unk4 integer);

require 'snmp'
require 'dbi'
require 'cgi' # Only for escapeHTML

SNMP::MIB.import_module('RICOH-MIB.txt')

version = "0.8 (beta)"

#
# Parameter block
#
printer_ip = '10.92.96.20'
epoch = '20'
past_months = 12
summary_report_filename = "/usr/share/nginx/www/summary.html"
printer_name = nil

DBI.connect('dbi:SQLite3:print_jobs.sqlite') { |dbh|
  SNMP::Manager.open(:Host => printer_ip, :mib_modules => [ 'SNMPv2-MIB', 'RICOH-MIB' ] ) do |mgr|
    printer_name = "#{mgr.get_value('sysDescr.0')} @ #{printer_ip} via SNMP"
    puts "Fetching job list information from printer '#{printer_name}' @ '#{printer_ip}'"
    mgr.walk( [
               'ricohJobUnk1',
               'ricohJobUserId', 
               'ricohJobFilename', 
               'ricohJobUnk2',
               'ricohJobPages',
               'ricohJobId',
               'ricohJobTimestamp', 
               'ricohJobAuthenticationInfo', 
               'ricohJobStateText',
               'ricohJobState',
               'ricohJobUnk3',
               'ricohJobUnk4'
              ]) do |unk1, user_id, filename, unk2, pages, job_id, ts, auth_info, state_text, state, unk3, unk4|
      # puts "Found job: user='#{user_id.value}' filename='#{filename.value}' pages='#{pages.value}' auth_info='#{auth_info.value}' job_id='#{job_id.value}' ts='#{ts.value}' state='#{state.value}'"

      # Skip empty slots
      if state.value == 0 then next end

      # Determine unique job ID, first try to extract from the 
      uid = job_id.value.split(',').select { |kvp| /^submit=/.match(kvp) }.first
      if uid == 'submit=(NONE)' then
        # Submit info not present, we need to generate based on job sequence ID and file name
        pid=job_id.value.split(',').select { |kvp| /^pid=/.match(kvp) }.first
        uid = "#{pid},filename=#{filename.value.encode!('UTF-8', 'ISO-8859-2')}"
      end

      # Determine job timestamp
      ctime = /^submit=(.+)/.match(ts.value)[1]
      if ctime == 'xx' then
        ctime = Time.new.gmtime.strftime '%Y-%m-%dT%H:%MZ'
      else
        # Convert to a ISO-8601 syntax variant acceptable by sqlite
        ctime = "#{epoch}#{ctime[0,2]}-#{ctime[2,2]}-#{ctime[4,2]}T#{ctime[6,2]}:#{ctime[8,2]}Z"
      end

      # Put all info into sqlite
      dbh.do('insert or ignore into print_jobs( _uid, _ctime, Unk1, UserId, Filename, Unk2, Pages, JobId, Timestamp, AuthenticationInfo, StateText, State, Unk3, Unk4 ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', 
             uid, ctime, unk1.value, user_id.value, filename.value.encode!('UTF-8', 'ISO-8859-2'), unk2.value, pages.value, job_id.value, ts.value, auth_info.value, state_text.value.encode!('UTF-8', 'ISO-8859-2'), Integer(state.value), Integer(unk3.value), Integer(unk4.value))
    end
  end

  # Now generate a summary

  File.open(summary_report_filename, "w") { |report|
    report.puts(<<-html)
<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Printerstasi</title></head>
<body>
<h1>Das Printerstasi v#{version}</h1>
<p>Job list summary for #{printer_name}</p>
<p>This summary was generated @ #{Time.now.gmtime.strftime("%Y-%m-%d %H:%M:%SZ")} and covers past #{past_months} months.</p>
html

    summary = Hash.new { |h,k| h[k] = Array.new }

    dbh.select_all("select substr(substr(AuthenticationInfo,1,instr(AuthenticationInfo,',')-1),length('username=')+1) as user,sum( substr(Pages,instr(Pages,'prt=')+length('prt=')) ) as total_pages,datetime(_ctime,'start of month') as month from print_jobs group by user,month having month > datetime('now', '-#{past_months} months') order by month,total_pages desc;") { |user,total_pages,month| 
      
      summary[month] << { 'user' => user, 'total_pages' => total_pages.to_i }
    }

    summary.each_pair { |month,entries| 
      report.puts(<<html)
<p>
Pages printed summary for #{month}
<table>
<thead><tr><th>Login</th><th>Page count</th></tr>
<tbody>
html

      entries.each { |entry| report.puts ("<tr><td>#{entry['user']}</td><td>#{entry['total_pages']}</td></tr>") }

      report.puts(<<html)
</tbody></table></p>
html

    }
    report.puts(<<-html)
</tbody>
</table></p>
</body>
</html>
html

  }

}


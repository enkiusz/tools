#!/usr/bin/env ruby

## Category: Daily/maintenance
## Shortdesc: Generate the README.md file based on Category and Shortdesc entries inside scripts.

categories = {}

ARGV.each do |filename|
  File.open(filename) do |f|
    cat = f.each_line.grep(/^## Category: .+/ )
    f.seek(0)
    desc = f.each_line.grep(/^## Shortdesc: .+/ )
    if !cat.first or !desc.first
      next
    end

    cat = cat.first[/^## Category: (.+)/,1]
    desc = desc.first[/^## Shortdesc: (.+)/,1]
    categories[cat] = [] if not categories.has_key?(cat)
    categories[cat].push({filename: filename, shortdesc: desc})
  end
end

categories.keys.sort.each do |cat|
  puts("## #{cat}:")
  categories[cat].each do |s|
    puts("* #{s[:filename]} - #{s[:shortdesc]}")
  end
  puts("")
end

# WingDBG
Eggification of Wingware WingDBG a Zope product that allows Wing to debug Python code running under Zope2

# Fast start-up
For all detailed documentation, please follow: http://www.wingware.com/doc/howtos/zope

Update your buildout configuration:
 1) adding WingDBG to your eggs
 ```
 eggs +=
   WingDBG
   
  ```
 2) enabling product installation 
```
[instance]
recipe = plone.recipe.zope2instance
[...]
enable-product-installation = on
```

Then run buildout (usually `bin/buildout -Nv`) and start Zope (i.e. `bin/instance fg`).
You should see something like `2018-03-27 09:26:02 INFO WingDBG Installed Wing Debug Service in Control Panel` 
just before classic `Zope Ready to handle requests`

Now go to the Control_Panel in ZMI and follow the new link "Wing Debug Service". 
Here you can start the servive, it will connect automatically to your wing editor (for remote debugging see official documentation)

If something fails check the `wing home dir` in the `configure` tab. It should be something like
`/usr/lib/wingide6` or `/usr/local/lib/wingide6.0`
depending on your WingIDE installation. That path is created and populated during WingIDE editor installation.

Go to your localhost:50080 and enjoy your live breakpoints ;)

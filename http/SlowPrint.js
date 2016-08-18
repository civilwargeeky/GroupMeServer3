/***************************
This is JavaScript (JS), the programming language that powers the web (and this is a comment, which you can delete).

To use this file, link it to your markup by placing a <script> in the <body> of your HTML file:

  <body>
    <script src="script.js"></script>

replacing "script.js" with the name of this JS file.

Learn more about JavaScript at

https://developer.mozilla.org/en-US/Learn/JavaScript
***************************/

var spCount = 0;

function sp(element, message, time, single) {
  var element = document.getElementById(element);
  var message = message || element.innerHTML;
  var speed = (time || 1.5)*1000/message.length;
  if (single === undefined) {single = false;}
  element.innerHTML = null;

  var i = 0;
  //Add another to count of currently running
  spCount++;
  var interval = setInterval(function() {
    //If single, checks if another is printing and may terminate
    if ((i > message.length) || (single && (spCount > 1))){
      clearInterval(interval);
      spCount--;
      return false; //So another char isn't executed
    }
    element.innerHTML += message.charAt(i);
    i++;
  }, speed);
}

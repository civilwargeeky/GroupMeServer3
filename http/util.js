/***************************
This is JavaScript (JS), the programming language that powers the web (and this is a comment, which you can delete).

To use this file, link it to your markup by placing a <script> in the <body> of your HTML file:

  <body>
    <script src="script.js"></script>

replacing "script.js" with the name of this JS file.

Learn more about JavaScript at

https://developer.mozilla.org/en-US/Learn/JavaScript
***************************/

function toggleClass(object, word) {
  if (object !== null) {
    if(object.className.indexOf(word) >= 0){
      //Replace the word (and optional space) with a blank string
      object.className = object.className.replace(new RegExp(word + " ?","g"),"");
    } else {
      object.className = word + " " + object.className;
    }
    console.log("New Class Name: ",object.className);
  }
  return object;
}


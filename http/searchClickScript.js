window.onload = function() {
  //This goes through all the things and sets their onclick function
  var elements = document.getElementsByTagName("tr")
  console.log("Starting Thing");
  for (i in elements) {
    console.log(elements[i].className);
    if (elements[i].className) {
      elements[i].onclick=function () {
        if (!this.id) {return false;}
        console.log("Click engaged!");
        console.log("Element Clicked: ",this.id);
        //This is so its the same no matter what
        var main = document.getElementById(/\d+/.exec(this.id)[0]);
        toggleClass(main, "SearchFocus");
        var i = 0;
        while (document.getElementById(main.id+" "+i) !== null) {
          console.log("Getting: ", main.id[0]+" "+i);
          toggleClass(document.getElementById(main.id+" "+i), "SearchFocus");
          i += 1;
        }
      }
    }
  }
}
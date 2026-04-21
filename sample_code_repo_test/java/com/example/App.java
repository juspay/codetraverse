package com.example;

import com.example.model.Person;
import com.example.utils.StringHelper;
import static com.example.utils.MathHelper.*;

public class App {
    
    public static void main(String[] args) {
        Person person = new Person("John", 30);
        person.greet();
        
        String greeting = StringHelper.createGreeting("World");
        System.out.println(greeting);
        
        int result = add(5, 3);
        System.out.println(result);
    }
    
    public void run() {
        Person p = new Person("Alice", 25);
        p.greet();
    }
}

package com.example.model;

public class Person {
    private String name;
    private int age;
    
    public Person(String name, int age) {
        this.name = name;
        this.age = age;
    }
    
    public void greet() {
        System.out.println("Hello, " + name);
    }
    
    public String getName() {
        return name;
    }
    
    public int getAge() {
        return age;
    }
}
